#!/usr/local/miniconda3/bin/python3.9
"""Run the calibrated detector and publish 640x360 RGB frames via shared memory."""

from __future__ import annotations

import argparse
import signal
import struct
import sys
import time
from multiprocessing import resource_tracker, shared_memory
from types import SimpleNamespace


CAMERA_PROJECT_DIR = "/home/HwHiAiUser/Desktop/RBCC/RBCC_Camera"
CONTROL_FORMAT = "<QIIIfiii"
running = True


def stop_worker(_signum=None, _frame=None) -> None:
    global running
    running = False


def attach_shared_memory(name: str):
    block = shared_memory.SharedMemory(name=name)
    # The dashboard owns these segments. Do not let the attaching worker's
    # resource tracker unlink them when the worker exits.
    try:
        resource_tracker.unregister(block._name, "shared_memory")
    except Exception:
        pass
    return block


def resize_rgb(cv2, frame, width: int, height: int) -> bytes:
    source_height, source_width = frame.shape[:2]
    interpolation = cv2.INTER_AREA if source_width > width or source_height > height else cv2.INTER_LINEAR
    resized = cv2.resize(frame, (width, height), interpolation=interpolation)
    return cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).tobytes()


def detect_white_marker(detector, frame):
    """Track the pale red block inside the camera's fixed 0-30 work area.

    The live feed is intentionally bright enough that the block's centre is
    almost white. Its edges retain a small red/pink chroma, however, while the
    white frame and marker dot do not. Closing those edge pixels recovers one
    stable square without confusing the long LED glare for the tracked block.
    """
    cv2 = detector.cv2
    np = detector.np
    # Keep contour sizes and thresholds independent of the capture mode. The
    # camera currently supplies 1280x720 while the shared preview is 640x360.
    frame = cv2.resize(frame, (640, 360), interpolation=cv2.INTER_AREA)
    height, width = frame.shape[:2]
    left = round(width * 0.14)
    right = round(width * 0.60)
    top = round(height * 0.14)
    bottom = round(height * 0.56)
    roi = frame[top:bottom, left:right]
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    red_low = cv2.inRange(
        hsv,
        np.array((0, 12, 120), dtype=np.uint8),
        np.array((18, 150, 255), dtype=np.uint8),
    )
    red_high = cv2.inRange(
        hsv,
        np.array((165, 12, 120), dtype=np.uint8),
        np.array((179, 150, 255), dtype=np.uint8),
    )
    mask = cv2.bitwise_or(red_low, red_high)
    mask = cv2.morphologyEx(
        mask,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)),
    )
    mask = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if not 180.0 <= area <= 3000.0:
            continue
        x, y, box_width, box_height = cv2.boundingRect(contour)
        if box_width < 10 or box_height < 10:
            continue
        side_ratio = min(box_width, box_height) / max(box_width, box_height)
        fill_ratio = area / max(1.0, float(box_width * box_height))
        if side_ratio < 0.58 or fill_ratio < 0.48:
            continue
        candidates.append((area * side_ratio * fill_ratio, x, y, box_width, box_height))
    if not candidates:
        return None
    _, x, y, box_width, box_height = max(candidates)
    center_x = left + x + box_width / 2.0
    center_y = top + y + box_height / 2.0
    coordinate_x = round(max(0.0, min(60.0, (center_x - left) / (right - left) * 60.0)))
    coordinate_y = round(max(0.0, min(30.0, (bottom - center_y) / (bottom - top) * 30.0)))
    return coordinate_x, coordinate_y


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=360)
    parser.add_argument("--original-shm", required=True)
    parser.add_argument("--result-shm", required=True)
    parser.add_argument("--control-shm", required=True)
    args = parser.parse_args()

    if CAMERA_PROJECT_DIR not in sys.path:
        sys.path.insert(0, CAMERA_PROJECT_DIR)
    import white_object_detector as detector

    detector.configure_logging(f"{CAMERA_PROJECT_DIR}/integrated_detector.log")
    detector.cv2.setUseOptimized(True)
    detector.cv2.setNumThreads(max(1, min(2, detector.cv2.getNumberOfCPUs())))
    signal.signal(signal.SIGTERM, stop_worker)
    signal.signal(signal.SIGINT, stop_worker)

    original_shm = attach_shared_memory(args.original_shm)
    result_shm = attach_shared_memory(args.result_shm)
    control_shm = attach_shared_memory(args.control_shm)
    frame_bytes = args.width * args.height * 3
    camera = None
    tracker = None
    try:
        camera_args = SimpleNamespace(
            device=detector.DEFAULT_CAMERA_DEVICE,
            frame_width=1280,
            frame_height=720,
            frame_rate=20,
        )
        config = detector.Config()
        # The camera is fixed, and the robust white-frame search is CPU-heavy.
        # Recheck roughly every two minutes at the measured 15-17 FPS.
        tracker = detector.ReferenceTracker(search_interval=1800)
        camera = detector.open_camera(camera_args)
        for _ in range(5):
            ok, _frame = camera.read()
            if not ok:
                raise RuntimeError("摄像头预热失败")

        sequence = 0
        frame_count = 0
        fps_started = time.monotonic()
        fps = 0.0
        while running:
            started = time.monotonic()
            ok, frame = camera.read()
            if not ok:
                raise RuntimeError("摄像头读取失败")
            measured = detector.draw_measurements(frame, config, tracker)
            measurements = getattr(detector, "LAST_MEASUREMENTS", [])
            target = next(
                (item for item in measurements if item.kind in ("heavy_block", "lifted_object")),
                None,
            )
            if target is not None:
                # Once the calibrated detector has a red heavy block, publish
                # its physical 60 x 30 cm coordinates and ignore the direct
                # image-space fallback (which can be distracted by red LEDs).
                center = target.box.mean(axis=0)
                x_cm = float(center[0]) / config.pixels_per_cm
                y_cm = config.background_height_cm - float(center[1]) / config.pixels_per_cm
                position_x = round(max(0.0, min(60.0, x_cm)))
                position_y = round(max(0.0, min(30.0, y_cm)))
                position_valid = 1
            else:
                # Do not fall back to an uncalibrated red-pixel search here.
                # In the illuminated installation that path can lock onto a
                # strip LED and publish a plausible but wrong X=0 position.
                # The dashboard/STM32 retain the last confirmed lamp state
                # across a transient detector miss.
                position_x, position_y = -1, -1
                position_valid = 0
            original_rgb = resize_rgb(detector.cv2, frame, args.width, args.height)
            result_rgb = resize_rgb(detector.cv2, measured, args.width, args.height)

            sequence += 1
            slot = sequence & 1
            offset = slot * frame_bytes
            original_shm.buf[offset:offset + frame_bytes] = original_rgb
            result_shm.buf[offset:offset + frame_bytes] = result_rgb

            frame_count += 1
            elapsed = time.monotonic() - fps_started
            if elapsed >= 1.0:
                fps = frame_count / elapsed
                frame_count = 0
                fps_started = time.monotonic()
            # Publish metadata last so the GUI only reads completed frame slots.
            struct.pack_into(
                CONTROL_FORMAT, control_shm.buf, 0,
                sequence, args.width, args.height, frame_bytes, fps,
                position_valid, position_x, position_y,
            )
            delay = 0.05 - (time.monotonic() - started)
            if delay > 0:
                time.sleep(delay)
    except Exception as exc:
        print(f"camera worker failed: {exc}", file=sys.stderr, flush=True)
        return 1
    finally:
        if camera is not None:
            camera.release()
        if tracker is not None:
            tracker.close()
        original_shm.close()
        result_shm.close()
        control_shm.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
