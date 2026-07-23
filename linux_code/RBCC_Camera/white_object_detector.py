#!/usr/bin/env python3
"""Detect red heavy blocks and yellow workers inside a known factory frame."""

from __future__ import annotations

import argparse
import itertools
import logging
import os
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field

import cv2
import numpy as np


LOGGER = logging.getLogger("rbcc_detector")
DETECTOR_VERSION = "white-frame-red-block-v3-20260720"


def configure_logging(log_file: str) -> None:
    """Log to both the terminal and a fresh per-run diagnostic file."""
    LOGGER.setLevel(logging.INFO)
    LOGGER.handlers.clear()
    formatter = logging.Formatter(
        "%(asctime)s.%(msecs)03d %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    LOGGER.addHandler(stream_handler)
    if log_file:
        file_handler = logging.FileHandler(log_file, mode="w", encoding="utf-8")
        file_handler.setFormatter(formatter)
        LOGGER.addHandler(file_handler)
    LOGGER.info("DETECTOR version=%s", DETECTOR_VERSION)


DEFAULT_CAMERA_DEVICE = (
    "/dev/v4l/by-id/"
    "usb-HD_Camera_Manufacturer_USB_2.0_Camera-video-index0"
)
DEFAULT_CAMERA_EXPOSURE = 90.0
LAST_MEASUREMENTS = []

# Physical size enclosed by the white factory boundary.
DEFAULT_BACKGROUND_WIDTH_CM = 60.0
DEFAULT_BACKGROUND_HEIGHT_CM = 30.0


@dataclass
class Config:
    """Runtime parameters, expressed in physical units where possible."""

    background_width_cm: float = DEFAULT_BACKGROUND_WIDTH_CM
    background_height_cm: float = DEFAULT_BACKGROUND_HEIGHT_CM
    pixels_per_cm: int = 12
    black_value_max: int = 120
    white_value_min: int = 175
    white_saturation_max: int = 60
    min_object_area_cm2: float = 1.0
    reference_white_value_min: int = 150
    reference_white_saturation_max: int = 85
    reference_min_area_ratio: float = 0.14
    reference_max_area_ratio: float = 0.35
    yellow_hue_min: int = 18
    yellow_hue_max: int = 42
    yellow_saturation_min: int = 30
    yellow_value_min: int = 130
    helmet_overexposed_saturation_max: int = 65
    helmet_overexposed_value_min: int = 150
    worker_min_diameter_cm: float = 0.7
    worker_max_diameter_cm: float = 4.0
    worker_min_circularity: float = 0.62
    worker_min_circle_fill: float = 0.50
    worker_min_side_ratio: float = 0.50
    worker_min_value_contrast: float = 35.0
    worker_min_yellow_fraction: float = 0.01
    worker_max_surrounding_value: float = 110.0
    worker_confirmation_frames: int = 2
    worker_max_missed_frames: int = 4
    worker_match_distance_cm: float = 2.5
    worker_smoothing_alpha: float = 0.35
    lifted_object_min_area_cm2: float = 4.0
    red_hue_low_max: int = 12
    red_hue_high_min: int = 168
    red_saturation_min: int = 70
    red_value_min: int = 70
    heavy_block_min_side_cm: float = 3.5
    heavy_block_max_side_cm: float = 6.8
    heavy_block_min_fill_ratio: float = 0.68
    heavy_block_min_side_ratio: float = 0.68
    heavy_block_match_distance_cm: float = 4.0


@dataclass
class Measurement:
    """One detected competition object in the rectified floor plane."""

    box: np.ndarray
    length_cm: float
    width_cm: float
    area_px: float
    kind: str
    circle_center: np.ndarray | None = None
    circle_radius_px: float = 0.0
    worker_id: int | None = None


@dataclass
class WorkerTrack:
    """A yellow-helmet observation stabilized in the rectified floor plane."""

    center: np.ndarray
    radius_px: float
    area_px: float
    worker_id: int
    hits: int = 1
    misses: int = 0


@dataclass
class HeavyBlockTrack:
    """A red heavy block stabilized in the rectified factory plane."""

    box: np.ndarray
    length_cm: float
    width_cm: float
    area_px: float
    block_id: int
    hits: int = 1
    misses: int = 0


@dataclass
class WorkerStabilizer:
    """Confirm, associate, and smooth factory objects across video frames."""

    tracks: list[WorkerTrack] = field(default_factory=list)
    next_worker_id: int = 1
    heavy_tracks: list[HeavyBlockTrack] = field(default_factory=list)
    next_block_id: int = 1

    def reset(self) -> None:
        self.tracks.clear()
        self.next_worker_id = 1
        self.heavy_tracks.clear()
        self.next_block_id = 1

    @staticmethod
    def _as_measurement(track: WorkerTrack, config: Config) -> Measurement:
        radius = float(track.radius_px)
        center = track.center.astype(np.float32)
        x, y = center
        box = np.array(
            [
                [x - radius, y - radius],
                [x + radius, y - radius],
                [x + radius, y + radius],
                [x - radius, y + radius],
            ],
            dtype=np.float32,
        )
        diameter_cm = 2.0 * radius / config.pixels_per_cm
        return Measurement(
            box=box,
            length_cm=diameter_cm,
            width_cm=diameter_cm,
            area_px=float(track.area_px),
            kind="worker",
            circle_center=center.copy(),
            circle_radius_px=radius,
            worker_id=track.worker_id,
        )

    def update(
        self,
        measurements: list[Measurement],
        config: Config,
    ) -> list[Measurement]:
        """Return temporally stable heavy blocks and worker helmets."""
        legacy_objects = [
            item for item in measurements if item.kind == "lifted_object"
        ]
        heavy_blocks = [
            item for item in measurements if item.kind == "heavy_block"
        ]
        workers = [
            item
            for item in measurements
            if item.kind == "worker" and item.circle_center is not None
        ]

        # Associate globally from the shortest distance so two nearby workers
        # cannot both update the same track.
        maximum_distance = (
            config.worker_match_distance_cm * config.pixels_per_cm
        )
        possible_matches: list[tuple[float, int, int]] = []
        for track_index, track in enumerate(self.tracks):
            for detection_index, worker in enumerate(workers):
                distance = float(
                    np.linalg.norm(worker.circle_center - track.center)
                )
                if distance <= maximum_distance:
                    possible_matches.append(
                        (distance, track_index, detection_index)
                    )
        possible_matches.sort(key=lambda item: item[0])

        matched_tracks: set[int] = set()
        matched_detections: set[int] = set()
        alpha = float(np.clip(config.worker_smoothing_alpha, 0.0, 1.0))
        for _distance, track_index, detection_index in possible_matches:
            if (
                track_index in matched_tracks
                or detection_index in matched_detections
            ):
                continue
            track = self.tracks[track_index]
            worker = workers[detection_index]
            track.center = (
                (1.0 - alpha) * track.center
                + alpha * worker.circle_center
            ).astype(np.float32)
            track.radius_px = (
                (1.0 - alpha) * track.radius_px
                + alpha * worker.circle_radius_px
            )
            track.area_px = (
                (1.0 - alpha) * track.area_px + alpha * worker.area_px
            )
            track.hits += 1
            track.misses = 0
            matched_tracks.add(track_index)
            matched_detections.add(detection_index)

        retained_tracks: list[WorkerTrack] = []
        for track_index, track in enumerate(self.tracks):
            if track_index not in matched_tracks:
                track.misses += 1
            confirmed = track.hits >= config.worker_confirmation_frames
            allowed_misses = (
                config.worker_max_missed_frames if confirmed else 0
            )
            if track.misses <= allowed_misses:
                retained_tracks.append(track)
        self.tracks = retained_tracks

        for detection_index, worker in enumerate(workers):
            if detection_index in matched_detections:
                continue
            self.tracks.append(
                WorkerTrack(
                    center=worker.circle_center.copy(),
                    radius_px=float(worker.circle_radius_px),
                    area_px=float(worker.area_px),
                    worker_id=self.next_worker_id,
                )
            )
            self.next_worker_id += 1

        stable_workers = [
            self._as_measurement(track, config)
            for track in self.tracks
            if track.hits >= config.worker_confirmation_frames
            and track.misses <= config.worker_max_missed_frames
        ]
        stable_workers.sort(
            key=lambda item: item.worker_id if item.worker_id is not None else 0
        )
        stable_blocks = self._update_heavy_blocks(heavy_blocks, config)
        legacy_objects.sort(key=lambda item: item.area_px, reverse=True)
        return legacy_objects + stable_blocks + stable_workers

    @staticmethod
    def _as_heavy_measurement(track: HeavyBlockTrack) -> Measurement:
        return Measurement(
            box=track.box.copy(),
            length_cm=float(track.length_cm),
            width_cm=float(track.width_cm),
            area_px=float(track.area_px),
            kind="heavy_block",
            worker_id=track.block_id,
        )

    def _update_heavy_blocks(
        self,
        detections: list[Measurement],
        config: Config,
    ) -> list[Measurement]:
        maximum_distance = (
            config.heavy_block_match_distance_cm * config.pixels_per_cm
        )
        possible_matches: list[tuple[float, int, int]] = []
        for track_index, track in enumerate(self.heavy_tracks):
            track_center = track.box.mean(axis=0)
            for detection_index, detection in enumerate(detections):
                distance = float(
                    np.linalg.norm(detection.box.mean(axis=0) - track_center)
                )
                if distance <= maximum_distance:
                    possible_matches.append(
                        (distance, track_index, detection_index)
                    )
        possible_matches.sort(key=lambda item: item[0])

        matched_tracks: set[int] = set()
        matched_detections: set[int] = set()
        alpha = float(np.clip(config.worker_smoothing_alpha, 0.0, 1.0))
        for _distance, track_index, detection_index in possible_matches:
            if (
                track_index in matched_tracks
                or detection_index in matched_detections
            ):
                continue
            track = self.heavy_tracks[track_index]
            detection = detections[detection_index]
            detection_box = order_corners(detection.box)
            track.box = (
                (1.0 - alpha) * track.box + alpha * detection_box
            ).astype(np.float32)
            track.length_cm = (
                (1.0 - alpha) * track.length_cm
                + alpha * detection.length_cm
            )
            track.width_cm = (
                (1.0 - alpha) * track.width_cm + alpha * detection.width_cm
            )
            track.area_px = (
                (1.0 - alpha) * track.area_px + alpha * detection.area_px
            )
            track.hits += 1
            track.misses = 0
            matched_tracks.add(track_index)
            matched_detections.add(detection_index)

        retained_tracks: list[HeavyBlockTrack] = []
        for track_index, track in enumerate(self.heavy_tracks):
            if track_index not in matched_tracks:
                track.misses += 1
            confirmed = track.hits >= config.worker_confirmation_frames
            allowed_misses = (
                config.worker_max_missed_frames if confirmed else 0
            )
            if track.misses <= allowed_misses:
                retained_tracks.append(track)
        self.heavy_tracks = retained_tracks

        for detection_index, detection in enumerate(detections):
            if detection_index in matched_detections:
                continue
            self.heavy_tracks.append(
                HeavyBlockTrack(
                    box=order_corners(detection.box),
                    length_cm=float(detection.length_cm),
                    width_cm=float(detection.width_cm),
                    area_px=float(detection.area_px),
                    block_id=self.next_block_id,
                )
            )
            self.next_block_id += 1

        stable_blocks = [
            self._as_heavy_measurement(track)
            for track in self.heavy_tracks
            if track.hits >= config.worker_confirmation_frames
            and track.misses <= config.worker_max_missed_frames
        ]
        stable_blocks.sort(
            key=lambda item: item.worker_id if item.worker_id is not None else 0
        )
        return stable_blocks


@dataclass
class BlackRectangle:
    """One factory-frame candidate before physical-size assignment.

    The legacy field names are retained because the Interface imports this
    module directly and older calibration helpers may still inspect them.
    """

    corners: np.ndarray
    score: float
    contains_white: bool
    area_ratio: float


@dataclass
class PerformanceLogger:
    """Aggregate frame timings and emit one compact line every few seconds."""

    backend: str
    report_interval_seconds: float = 2.0
    period_started: float = 0.0
    frames: int = 0
    capture_total_ms: float = 0.0
    process_total_ms: float = 0.0
    display_total_ms: float = 0.0
    process_max_ms: float = 0.0
    loop_max_ms: float = 0.0

    def __post_init__(self) -> None:
        self.period_started = time.perf_counter()

    def record(
        self,
        capture_ms: float,
        process_ms: float,
        display_ms: float,
        loop_ms: float,
        tracker: "ReferenceTracker",
    ) -> None:
        self.frames += 1
        self.capture_total_ms += capture_ms
        self.process_total_ms += process_ms
        self.display_total_ms += display_ms
        self.process_max_ms = max(self.process_max_ms, process_ms)
        self.loop_max_ms = max(self.loop_max_ms, loop_ms)
        now = time.perf_counter()
        elapsed = now - self.period_started
        if elapsed < self.report_interval_seconds:
            return
        divisor = max(1, self.frames)
        LOGGER.info(
            "PERF backend=%s fps=%.1f frames=%d capture_avg_ms=%.1f "
            "process_avg_ms=%.1f process_max_ms=%.1f display_avg_ms=%.1f "
            "loop_max_ms=%.1f reference_last_ms=%.1f",
            self.backend,
            self.frames / elapsed,
            self.frames,
            self.capture_total_ms / divisor,
            self.process_total_ms / divisor,
            self.process_max_ms,
            self.display_total_ms / divisor,
            self.loop_max_ms,
            tracker.last_search_duration_ms,
        )
        self.period_started = now
        self.frames = 0
        self.capture_total_ms = 0.0
        self.process_total_ms = 0.0
        self.display_total_ms = 0.0
        self.process_max_ms = 0.0
        self.loop_max_ms = 0.0


@dataclass
class ReferenceTracker:
    """Stabilize reference corners and avoid a full search on every frame."""

    corners: np.ndarray | None = None
    rectangles: list[np.ndarray] | None = None
    frame_index: int = 0
    missed_searches: int = 0
    search_interval: int = 60
    retry_interval: int = 30
    max_missed_searches: int = 3
    smoothing_alpha: float = 0.30
    last_search_duration_ms: float = 0.0
    last_search_frame: int = 0
    last_candidate_count: int = 0
    worker_stabilizer: WorkerStabilizer = field(default_factory=WorkerStabilizer)
    _executor: ThreadPoolExecutor = field(
        default_factory=lambda: ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="reference-search",
        ),
        init=False,
        repr=False,
    )
    _future: Future | None = field(default=None, init=False, repr=False)

    @staticmethod
    def _search_reference(
        frame: np.ndarray,
        config: Config,
        scheduled_frame: int,
    ) -> tuple[list[BlackRectangle], float, int]:
        search_started = time.perf_counter()
        rectangles = detect_black_rectangles(frame, config)
        duration_ms = (time.perf_counter() - search_started) * 1000.0
        return rectangles, duration_ms, scheduled_frame

    def _apply_search_result(
        self,
        detected_rectangles: list[BlackRectangle],
        frame_shape: tuple[int, ...],
    ) -> None:
        detected: np.ndarray | None = None
        selected_index = 0
        if detected_rectangles:
            if self.corners is None:
                marker_indices = [
                    index
                    for index, rectangle in enumerate(detected_rectangles)
                    if rectangle.contains_white
                ]
                if marker_indices:
                    selected_index = marker_indices[0]
                    detected = detected_rectangles[selected_index].corners
                elif self.missed_searches >= self.max_missed_searches:
                    # Permit geometry-only startup after several retries so an
                    # intentionally empty factory can still be monitored.
                    detected = detected_rectangles[0].corners
            else:
                selected_index = min(
                    range(len(detected_rectangles)),
                    key=lambda index: float(
                        np.linalg.norm(
                            detected_rectangles[index].corners - self.corners,
                            axis=1,
                        ).mean()
                    ),
                )
                detected = detected_rectangles[selected_index].corners
        if detected is None:
            self.missed_searches += 1
            if self.missed_searches > self.max_missed_searches:
                self.corners = None
                self.rectangles = None
            return

        ordered_rectangles = (
            [detected_rectangles[selected_index]]
            + detected_rectangles[:selected_index]
            + detected_rectangles[selected_index + 1 :]
        )
        if self.corners is None:
            self.missed_searches = 0
            self.corners = detected
        else:
            diagonal = float(np.hypot(frame_shape[1], frame_shape[0]))
            mean_jump = float(
                np.linalg.norm(detected - self.corners, axis=1).mean()
            )
            if mean_jump > 0.12 * diagonal:
                self.missed_searches += 1
                LOGGER.warning(
                    "REFERENCE rejected jump mean_px=%.1f threshold_px=%.1f",
                    mean_jump,
                    0.12 * diagonal,
                )
                return
            else:
                self.missed_searches = 0
                alpha = self.smoothing_alpha
                self.corners = (
                    (1.0 - alpha) * self.corners + alpha * detected
                ).astype(np.float32)
        self.rectangles = [item.corners.copy() for item in ordered_rectangles]
        if self.rectangles:
            self.rectangles[0] = self.corners.copy()

    def update(self, frame: np.ndarray, config: Config) -> np.ndarray | None:
        self.frame_index += 1

        # Poll the worker without blocking the camera/Tk main thread.
        if self._future is not None and self._future.done():
            try:
                rectangles, duration_ms, scheduled_frame = self._future.result()
            except Exception:
                LOGGER.exception("REFERENCE background search failed")
                rectangles = []
                duration_ms = 0.0
                scheduled_frame = self.frame_index
            self._future = None
            self.last_search_duration_ms = duration_ms
            self.last_search_frame = scheduled_frame
            self.last_candidate_count = len(rectangles)
            LOGGER.info(
                "REFERENCE scheduled_frame=%d completed_frame=%d "
                "duration_ms=%.1f candidates=%d found=%s",
                scheduled_frame,
                self.frame_index,
                duration_ms,
                len(rectangles),
                bool(rectangles),
            )
            self._apply_search_result(rectangles, frame.shape)

        # Schedule immediately once, then at a fixed interval.  Copying one
        # frame prevents the capture buffer from changing under the worker.
        should_search = (
            self.frame_index == 1
            or (
                self.corners is None
                and self.frame_index - self.last_search_frame
                >= self.retry_interval
            )
            or self.frame_index % self.search_interval == 0
        )
        if should_search and self._future is None:
            scheduled_frame = self.frame_index
            self._future = self._executor.submit(
                self._search_reference,
                frame.copy(),
                config,
                scheduled_frame,
            )
            LOGGER.info("REFERENCE scheduled_frame=%d", scheduled_frame)

        return None if self.corners is None else self.corners.copy()

    def reset_reference(self) -> None:
        """Discard invalid geometry and request another search immediately."""
        self.corners = None
        self.rectangles = None
        self.frame_index = 0
        self.missed_searches = 0
        self.worker_stabilizer.reset()

    def close(self) -> None:
        """Release the background worker without blocking window shutdown."""
        self._executor.shutdown(wait=False, cancel_futures=True)


def order_corners(points: np.ndarray) -> np.ndarray:
    """Order four image points as top-left, top-right, bottom-right, bottom-left."""
    points = np.asarray(points, dtype=np.float32).reshape(4, 2)
    ordered = np.zeros((4, 2), dtype=np.float32)
    point_sums = points.sum(axis=1)
    point_differences = np.diff(points, axis=1).reshape(-1)
    ordered[0] = points[np.argmin(point_sums)]
    ordered[2] = points[np.argmax(point_sums)]
    ordered[1] = points[np.argmin(point_differences)]
    ordered[3] = points[np.argmax(point_differences)]
    return ordered


def draw_text_labels(
    image: np.ndarray,
    labels: list[tuple[str, tuple[int, int], tuple[int, int, int], int]],
) -> np.ndarray:
    """Draw lightweight ASCII labels with an outlined OpenCV font."""
    for text, (x, y), bgr_color, size in labels:
        scale = size / 32.0
        (text_width, text_height), _ = cv2.getTextSize(
            text,
            cv2.FONT_HERSHEY_SIMPLEX,
            scale,
            2,
        )
        x = int(np.clip(x, 5, max(5, image.shape[1] - text_width - 5)))
        baseline_y = int(
            np.clip(y + size, text_height + 5, image.shape[0] - 5)
        )
        baseline_position = (x, baseline_y)
        cv2.putText(
            image,
            text,
            baseline_position,
            cv2.FONT_HERSHEY_SIMPLEX,
            scale,
            (0, 0, 0),
            5,
            cv2.LINE_AA,
        )
        cv2.putText(
            image,
            text,
            baseline_position,
            cv2.FONT_HERSHEY_SIMPLEX,
            scale,
            bgr_color,
            2,
            cv2.LINE_AA,
        )
    return image


def quadrilateral_iou(first: np.ndarray, second: np.ndarray) -> float:
    """Return intersection-over-union for two convex quadrilaterals."""
    first = np.asarray(first, dtype=np.float32)
    second = np.asarray(second, dtype=np.float32)
    first_area = abs(float(cv2.contourArea(first)))
    second_area = abs(float(cv2.contourArea(second)))
    intersection_area, _ = cv2.intersectConvexConvex(first, second)
    union_area = first_area + second_area - float(intersection_area)
    return 0.0 if union_area <= 0 else float(intersection_area) / union_area


def fit_perspective_quadrilateral(contour: np.ndarray) -> np.ndarray:
    """Fit four independent boundary lines to a perspective rectangle.

    ``minAreaRect`` forces opposite sides to be parallel.  With the wide-angle
    camera and an oblique board that can push a fitted corner outside the
    image, even though the rounded board itself is fully visible.  The convex
    hull is first grouped by the four min-area-box sides; each group then gets
    its own line fit and adjacent lines are intersected.
    """
    hull = cv2.convexHull(contour).reshape(-1, 2).astype(np.float32)
    initial = order_corners(cv2.boxPoints(cv2.minAreaRect(hull)))
    if len(hull) < 8:
        return initial

    distances: list[np.ndarray] = []
    for index in range(4):
        start = initial[index]
        edge = initial[(index + 1) % 4] - start
        edge_length = float(np.linalg.norm(edge))
        if edge_length <= 1e-6:
            return initial
        relative = hull - start
        cross = edge[0] * relative[:, 1] - edge[1] * relative[:, 0]
        distances.append(np.abs(cross) / edge_length)
    assignments = np.argmin(np.vstack(distances), axis=0)

    lines: list[tuple[np.ndarray, np.ndarray]] = []
    for index in range(4):
        side_points = hull[assignments == index]
        if len(side_points) < 2:
            return initial
        vx, vy, x, y = cv2.fitLine(
            side_points, cv2.DIST_L2, 0, 0.01, 0.01
        ).reshape(-1)
        lines.append(
            (
                np.array((x, y), dtype=np.float32),
                np.array((vx, vy), dtype=np.float32),
            )
        )

    def line_intersection(
        first: tuple[np.ndarray, np.ndarray],
        second: tuple[np.ndarray, np.ndarray],
    ) -> np.ndarray | None:
        first_point, first_direction = first
        second_point, second_direction = second
        denominator = (
            first_direction[0] * second_direction[1]
            - first_direction[1] * second_direction[0]
        )
        if abs(float(denominator)) < 1e-5:
            return None
        offset = second_point - first_point
        distance = (
            offset[0] * second_direction[1]
            - offset[1] * second_direction[0]
        ) / denominator
        return first_point + distance * first_direction

    fitted_points = [
        line_intersection(lines[3], lines[0]),
        line_intersection(lines[0], lines[1]),
        line_intersection(lines[1], lines[2]),
        line_intersection(lines[2], lines[3]),
    ]
    if any(point is None for point in fitted_points):
        return initial
    fitted = np.asarray(fitted_points, dtype=np.float32)
    if not np.all(np.isfinite(fitted)) or not cv2.isContourConvex(fitted):
        return initial

    initial_area = abs(float(cv2.contourArea(initial)))
    fitted_area = abs(float(cv2.contourArea(fitted)))
    if not 0.55 * initial_area <= fitted_area <= 1.25 * initial_area:
        return initial
    return order_corners(fitted)


def _detect_legacy_black_rectangles(
    frame: np.ndarray,
    config: Config,
) -> list[BlackRectangle]:
    """Find all complete, compact dark rectangles without an aspect-ratio rule."""
    # Reference detection does not need full camera resolution.  Working on a
    # smaller image makes the multi-threshold search fast enough for live use.
    max_dimension = max(frame.shape[:2])
    detection_scale = min(1.0, 720.0 / max_dimension)
    if detection_scale < 1.0:
        analysis_frame = cv2.resize(
            frame,
            None,
            fx=detection_scale,
            fy=detection_scale,
            interpolation=cv2.INTER_AREA,
        )
    else:
        analysis_frame = frame

    hsv = cv2.cvtColor(analysis_frame, cv2.COLOR_BGR2HSV)
    value_channel = hsv[:, :, 2]
    frame_height, frame_width = value_channel.shape
    frame_area = frame_height * frame_width

    # White regions help rank the main measurement reference, but are not a
    # hard requirement for detecting and drawing other black rectangles.
    white_mask = cv2.inRange(
        hsv,
        np.array((0, 0, config.white_value_min), dtype=np.uint8),
        np.array((179, max(80, config.white_saturation_max), 255), dtype=np.uint8),
    )
    white_contours, _ = cv2.findContours(
        white_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    white_candidates: list[tuple[float, tuple[float, float]]] = []
    for contour in white_contours:
        area = cv2.contourArea(contour)
        x, y, width, height = cv2.boundingRect(contour)
        touches_border = (
            x <= 2
            or y <= 2
            or x + width >= frame_width - 2
            or y + height >= frame_height - 2
        )
        if area >= frame_area * 0.001 and not touches_border:
            white_candidates.append(
                (area, (x + width / 2.0, y + height / 2.0))
            )
    anchors = [item[1] for item in white_candidates]
    ranking_anchor = (
        max(white_candidates, key=lambda item: item[0])[1]
        if white_candidates
        else (frame_width / 2.0, frame_height / 2.0)
    )

    # Large-scale smoothing removes the connected black fibres of the carpet
    # while retaining the much larger, uniformly dark reference object.
    blur_size = max(15, round(min(frame_height, frame_width) * 0.03))
    if blur_size % 2 == 0:
        blur_size += 1
    smoothed_value = cv2.GaussianBlur(
        value_channel, (blur_size, blur_size), 0
    )
    morphology_size = max(9, round(min(frame_height, frame_width) * 0.012))
    if morphology_size % 2 == 0:
        morphology_size += 1
    close_kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, (morphology_size, morphology_size)
    )
    # A chair/gantry leg can touch the dark reference in the threshold mask.
    # A larger opening disconnects such narrow appendages while preserving the
    # much wider reference surface and its rounded outer boundary.
    separation_size = max(
        15, round(min(frame_height, frame_width) * 0.075)
    )
    if separation_size % 2 == 0:
        separation_size += 1
    separation_kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, (separation_size, separation_size)
    )

    diagonal = float(np.hypot(frame_width, frame_height))
    candidates: list[BlackRectangle] = []

    # A single threshold is fragile on textured floors.  Search progressively
    # up to the configured upper limit.  Also try a lower brightness bound:
    # this separates a dark-grey/black reference from even darker clothes that
    # touch it in the image, instead of merging both into one border-connected
    # component.
    upper_threshold = int(np.clip(config.black_value_max, 35, 220))
    thresholds = list(range(25, upper_threshold + 1, 15))
    if thresholds[-1] != upper_threshold:
        thresholds.append(upper_threshold)

    for threshold in thresholds:
        lower_bounds = [0]
        lower_bounds.extend(range(15, max(16, threshold - 14), 15))

        for lower_bound in lower_bounds:
            black_mask = cv2.inRange(
                smoothed_value,
                lower_bound,
                threshold,
            )
            black_mask = cv2.morphologyEx(
                black_mask, cv2.MORPH_CLOSE, close_kernel
            )
            black_mask = cv2.morphologyEx(
                black_mask, cv2.MORPH_OPEN, separation_kernel
            )
            contours, _ = cv2.findContours(
                black_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )

            for contour in contours:
                contour_area = cv2.contourArea(contour)
                area_ratio = contour_area / frame_area
                if area_ratio < 0.01 or area_ratio > 0.85:
                    continue
                contour_x, contour_y, contour_width, contour_height = (
                    cv2.boundingRect(contour)
                )
                if (
                    contour_x <= 1
                    or contour_y <= 1
                    or contour_x + contour_width >= frame_width - 1
                    or contour_y + contour_height >= frame_height - 1
                ):
                    # A valid physical reference must be fully visible.  This
                    # rejects large room shadows/carpet regions that enter from
                    # an image edge, while still allowing fitted side lines to
                    # extrapolate slightly beyond a rounded reference corner.
                    continue

                rotated_rectangle = cv2.minAreaRect(cv2.convexHull(contour))
                side_a, side_b = rotated_rectangle[1]
                minimum_side = max(30.0, min(frame_height, frame_width) * 0.05)
                if min(side_a, side_b) < minimum_side:
                    continue
                rectangle_area = side_a * side_b
                fill_ratio = contour_area / rectangle_area
                if fill_ratio < 0.60:
                    continue

                corners = fit_perspective_quadrilateral(contour)
                # Independent side-line intersections may extend a fraction of
                # a pixel past the image although the rounded physical corner
                # is visible.  Allow a small extrapolation, then clip the
                # homography points back inside the valid frame.
                extrapolation_tolerance = max(
                    2.0, min(frame_height, frame_width) * 0.02
                )
                if (
                    np.any(corners[:, 0] < -extrapolation_tolerance)
                    or np.any(corners[:, 1] < -extrapolation_tolerance)
                    or np.any(
                        corners[:, 0]
                        > frame_width - 1 + extrapolation_tolerance
                    )
                    or np.any(
                        corners[:, 1]
                        > frame_height - 1 + extrapolation_tolerance
                    )
                ):
                    continue
                corners[:, 0] = np.clip(corners[:, 0], 1, frame_width - 2)
                corners[:, 1] = np.clip(corners[:, 1], 1, frame_height - 2)
                fitted_edge_lengths = np.linalg.norm(
                    np.roll(corners, -1, axis=0) - corners,
                    axis=1,
                )
                fitted_area = abs(float(cv2.contourArea(corners)))
                if (
                    not cv2.isContourConvex(corners)
                    or float(fitted_edge_lengths.min())
                    < 0.25 * minimum_side
                    or fitted_area < 0.20 * rectangle_area
                ):
                    continue

                contained_anchors = [
                    point
                    for point in anchors
                    # The opening operation can turn the dark surface into a
                    # C-shaped contour around a large white sheet.  Test the
                    # fitted outer rectangle so that the white hole still
                    # counts as being inside the reference.
                    if cv2.pointPolygonTest(corners, point, False) >= 0
                ]
                contains_white = bool(contained_anchors)
                contains_ranking_anchor = cv2.pointPolygonTest(
                    corners, ranking_anchor, False
                ) >= 0
                if contains_ranking_anchor:
                    anchor_penalty = 0.0
                elif contains_white:
                    anchor_penalty = 0.18
                else:
                    anchor_penalty = 0.40
                center_distance = np.linalg.norm(
                    np.asarray(rotated_rectangle[0])
                    - np.asarray(ranking_anchor)
                ) / diagonal
                # No physical aspect-ratio term is used here.  Reference width
                # and height are applied only after detection for cm scaling.
                score = (
                    1.2 * (1.0 - fill_ratio)
                    + 0.20 * center_distance
                    # When two dark rectangles contain the same white anchor,
                    # prefer the outer factory-floor reference rather than a
                    # small inner panel immediately around the white object.
                    - 0.65 * area_ratio
                    + 0.05 * (lower_bound / max(1, threshold))
                    + anchor_penalty
                )
                candidates.append(
                    BlackRectangle(
                        corners=corners,
                        score=float(score),
                        contains_white=contains_white,
                        area_ratio=float(area_ratio),
                    )
                )

    if not candidates:
        return []

    # The threshold sweep creates many nearly identical boxes for one physical
    # object.  Keep the best-scoring box and suppress overlapping duplicates.
    candidates.sort(
        key=lambda item: (
            not item.contains_white,
            -item.area_ratio if item.contains_white else 0.0,
            item.score,
        )
    )
    unique: list[BlackRectangle] = []
    for candidate in candidates:
        if any(
            quadrilateral_iou(candidate.corners, kept.corners) >= 0.55
            for kept in unique
        ):
            continue
        unique.append(candidate)
        if len(unique) >= 8:
            break
    for candidate in unique:
        candidate.corners = (
            candidate.corners / detection_scale
        ).astype(np.float32)
    return unique


def detect_factory_rectangles(
    frame: np.ndarray,
    config: Config,
) -> list[BlackRectangle]:
    """Recover the white 60 x 30 cm boundary from four supporting lines.

    The factory is an outlined white quadrilateral on a black surface.  Bright
    green crane LEDs cross the boundary and can join the white pixels into one
    misleading contour, so the boundary is reconstructed from two pairs of
    near-parallel Hough lines instead of using the largest white component.
    """
    max_dimension = max(frame.shape[:2])
    detection_scale = min(1.0, 720.0 / max_dimension)
    if detection_scale < 1.0:
        analysis_frame = cv2.resize(
            frame,
            None,
            fx=detection_scale,
            fy=detection_scale,
            interpolation=cv2.INTER_AREA,
        )
    else:
        analysis_frame = frame

    blurred = cv2.GaussianBlur(analysis_frame, (3, 3), 0)
    hsv = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)
    value_channel = hsv[:, :, 2]
    white_mask = cv2.inRange(
        hsv,
        np.array(
            (0, 0, config.reference_white_value_min), dtype=np.uint8
        ),
        np.array(
            (179, config.reference_white_saturation_max, 255),
            dtype=np.uint8,
        ),
    )
    # Green crane LEDs can drive the UVC auto-exposure low enough that the
    # nominally white tape is only V=40-80.  Recover narrow locally-bright tape
    # strokes with a morphological top-hat instead of globally lowering the
    # white threshold (which would turn most of the black cloth into white).
    contrast_kernel_size = max(
        9, round(min(analysis_frame.shape[:2]) * 0.05)
    )
    if contrast_kernel_size % 2 == 0:
        contrast_kernel_size += 1
    local_background = cv2.morphologyEx(
        value_channel,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE,
            (contrast_kernel_size, contrast_kernel_size),
        ),
    )
    local_contrast = cv2.subtract(value_channel, local_background)
    contrast_threshold = int(
        np.clip(np.percentile(local_contrast, 90.0), 6, 18)
    )
    contrast_mask = cv2.inRange(
        local_contrast,
        contrast_threshold,
        255,
    )
    contrast_mask[value_channel < 20] = 0
    # Do not add the noisier local-contrast mask to normally exposed frames;
    # it is strictly an underexposure fallback.
    if float(np.mean(white_mask > 0)) < 0.05:
        white_mask = cv2.bitwise_or(white_mask, contrast_mask)
    white_mask = cv2.morphologyEx(
        white_mask,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)),
    )

    frame_height, frame_width = white_mask.shape
    minimum_dimension = min(frame_height, frame_width)
    frame_area = frame_height * frame_width

    # A visible red block is a strong ranking anchor.  It is not mandatory,
    # because a valid game state may temporarily contain no heavy block.
    red_anchor_mask = cv2.bitwise_or(
        cv2.inRange(
            hsv,
            np.array(
                (0, config.red_saturation_min, config.red_value_min),
                dtype=np.uint8,
            ),
            np.array((config.red_hue_low_max, 255, 255), dtype=np.uint8),
        ),
        cv2.inRange(
            hsv,
            np.array(
                (
                    config.red_hue_high_min,
                    config.red_saturation_min,
                    config.red_value_min,
                ),
                dtype=np.uint8,
            ),
            np.array((179, 255, 255), dtype=np.uint8),
        ),
    )
    red_anchor_contours, _ = cv2.findContours(
        red_anchor_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    red_anchors: list[tuple[float, float]] = []
    for contour in red_anchor_contours:
        contour_area = cv2.contourArea(contour)
        if not frame_area * 0.00015 <= contour_area <= frame_area * 0.03:
            continue
        moments = cv2.moments(contour)
        if abs(moments["m00"]) <= 1.0e-6:
            continue
        red_anchors.append(
            (
                moments["m10"] / moments["m00"],
                moments["m01"] / moments["m00"],
            )
        )

    edges = cv2.Canny(white_mask, 40, 120)
    hough_lines = cv2.HoughLinesP(
        edges,
        1,
        np.pi / 720.0,
        threshold=max(24, round(minimum_dimension * 0.06)),
        minLineLength=max(35, round(minimum_dimension * 0.10)),
        maxLineGap=max(18, round(minimum_dimension * 0.075)),
    )
    if hough_lines is None:
        return []

    def angle_difference(first: float, second: float) -> float:
        difference = abs(first - second) % np.pi
        return min(difference, np.pi - difference)

    line_candidates: list[dict[str, float | tuple[float, ...]]] = []
    for raw_line in hough_lines[:, 0]:
        x1, y1, x2, y2 = (float(value) for value in raw_line)
        delta_x = x2 - x1
        delta_y = y2 - y1
        length = float(np.hypot(delta_x, delta_y))
        theta = float(np.arctan2(delta_y, delta_x) % np.pi)
        direction = np.array((np.cos(theta), np.sin(theta)))
        normal = np.array((-direction[1], direction[0]))
        midpoint = np.array(((x1 + x2) / 2.0, (y1 + y2) / 2.0))
        line_candidates.append(
            {
                "theta": theta,
                "rho": float(normal @ midpoint),
                "length": length,
                "weight": length,
                "segment": (x1, y1, x2, y2),
            }
        )
    line_candidates.sort(key=lambda item: float(item["length"]), reverse=True)

    # Merge the two visible edges of thick white tape and repeated Hough hits.
    clustered_lines: list[dict[str, float | tuple[float, ...]]] = []
    for candidate in line_candidates:
        matching_cluster = next(
            (
                cluster
                for cluster in clustered_lines
                if angle_difference(
                    float(candidate["theta"]), float(cluster["theta"])
                )
                < np.deg2rad(2.5)
                and abs(float(candidate["rho"]) - float(cluster["rho"]))
                < max(5.0, minimum_dimension * 0.015)
            ),
            None,
        )
        if matching_cluster is None:
            clustered_lines.append(candidate.copy())
            continue
        matching_cluster["weight"] = float(matching_cluster["weight"]) + float(
            candidate["length"]
        )
        if float(candidate["length"]) > float(matching_cluster["length"]):
            for key in ("theta", "rho", "length", "segment"):
                matching_cluster[key] = candidate[key]

    clustered_lines.sort(key=lambda item: float(item["weight"]), reverse=True)
    clustered_lines = clustered_lines[:60]

    def line_intersection(
        first: dict[str, float | tuple[float, ...]],
        second: dict[str, float | tuple[float, ...]],
    ) -> np.ndarray | None:
        first_theta = float(first["theta"])
        second_theta = float(second["theta"])
        first_normal = np.array((-np.sin(first_theta), np.cos(first_theta)))
        second_normal = np.array((-np.sin(second_theta), np.cos(second_theta)))
        coefficient_matrix = np.vstack((first_normal, second_normal))
        if abs(float(np.linalg.det(coefficient_matrix))) < 1.0e-4:
            return None
        return np.linalg.solve(
            coefficient_matrix,
            np.array((float(first["rho"]), float(second["rho"]))),
        ).astype(np.float32)

    support_thickness = max(5, round(minimum_dimension * 0.017))

    def edge_support(start: np.ndarray, end: np.ndarray) -> float:
        sample_mask = np.zeros_like(white_mask)
        cv2.line(
            sample_mask,
            tuple(np.rint(start).astype(int)),
            tuple(np.rint(end).astype(int)),
            255,
            support_thickness,
            cv2.LINE_AA,
        )
        sample_count = int(np.count_nonzero(sample_mask))
        if sample_count == 0:
            return 0.0
        return float(
            np.count_nonzero((sample_mask > 0) & (white_mask > 0))
            / sample_count
        )

    parallel_pairs: list[tuple[int, int, float]] = []
    for first_index, second_index in itertools.combinations(
        range(len(clustered_lines)), 2
    ):
        first = clustered_lines[first_index]
        second = clustered_lines[second_index]
        separation = abs(float(first["rho"]) - float(second["rho"]))
        if (
            angle_difference(float(first["theta"]), float(second["theta"]))
            <= np.deg2rad(6.0)
            and separation >= minimum_dimension * 0.11
        ):
            parallel_pairs.append((first_index, second_index, separation))

    expected_ratio = max(
        config.background_width_cm, config.background_height_cm
    ) / min(config.background_width_cm, config.background_height_cm)
    candidates: list[BlackRectangle] = []
    for first_pair, second_pair in itertools.combinations(parallel_pairs, 2):
        first_a, first_b, _ = first_pair
        second_a, second_b, _ = second_pair
        if len({first_a, first_b, second_a, second_b}) != 4:
            continue
        first_theta = float(clustered_lines[first_a]["theta"])
        second_theta = float(clustered_lines[second_a]["theta"])
        if abs(angle_difference(first_theta, second_theta) - np.pi / 2.0) > np.deg2rad(12.0):
            continue

        intersections = [
            line_intersection(
                clustered_lines[first_a], clustered_lines[second_a]
            ),
            line_intersection(
                clustered_lines[first_a], clustered_lines[second_b]
            ),
            line_intersection(
                clustered_lines[first_b], clustered_lines[second_b]
            ),
            line_intersection(
                clustered_lines[first_b], clustered_lines[second_a]
            ),
        ]
        if any(point is None for point in intersections):
            continue
        corners = np.asarray(intersections, dtype=np.float32)
        center = corners.mean(axis=0)
        corner_angles = np.arctan2(
            corners[:, 1] - center[1], corners[:, 0] - center[0]
        )
        corners = corners[np.argsort(corner_angles)]
        if not cv2.isContourConvex(corners):
            continue
        boundary_tolerance = max(12.0, minimum_dimension * 0.05)
        if (
            np.any(corners[:, 0] < -boundary_tolerance)
            or np.any(corners[:, 0] > frame_width + boundary_tolerance)
            or np.any(corners[:, 1] < -boundary_tolerance)
            or np.any(corners[:, 1] > frame_height + boundary_tolerance)
        ):
            continue

        area = abs(float(cv2.contourArea(corners)))
        area_ratio = area / frame_area
        if not (
            config.reference_min_area_ratio
            <= area_ratio
            <= config.reference_max_area_ratio
        ):
            continue
        edge_lengths = np.linalg.norm(
            np.roll(corners, -1, axis=0) - corners, axis=1
        )
        first_mean = float((edge_lengths[0] + edge_lengths[2]) / 2.0)
        second_mean = float((edge_lengths[1] + edge_lengths[3]) / 2.0)
        observed_ratio = max(first_mean, second_mean) / max(
            1.0, min(first_mean, second_mean)
        )
        if not 0.70 * expected_ratio <= observed_ratio <= 1.40 * expected_ratio:
            continue

        support_values = np.array(
            [
                edge_support(corners[index], corners[(index + 1) % 4])
                for index in range(4)
            ]
        )
        if float(support_values.min()) < 0.16 or float(support_values.mean()) < 0.36:
            continue

        interior_mask = np.zeros_like(white_mask)
        cv2.fillConvexPoly(
            interior_mask, np.rint(corners).astype(np.int32), 255
        )
        erosion_size = max(11, round(minimum_dimension * 0.042))
        if erosion_size % 2 == 0:
            erosion_size += 1
        interior_mask = cv2.erode(
            interior_mask,
            cv2.getStructuringElement(
                cv2.MORPH_ELLIPSE, (erosion_size, erosion_size)
            ),
        )
        interior_values = value_channel[interior_mask > 0]
        if interior_values.size == 0:
            continue
        dark_fraction = float(
            np.mean(interior_values < max(145, config.black_value_max + 25))
        )
        if dark_fraction < 0.50:
            continue

        line_coverage = float(
            np.mean(
                [
                    min(
                        1.0,
                        float(clustered_lines[index]["length"])
                        / max(1.0, float(edge_lengths.mean())),
                    )
                    for index in (first_a, first_b, second_a, second_b)
                ]
            )
        )
        contains_red = any(
            cv2.pointPolygonTest(corners, point, False) >= 0
            for point in red_anchors
        )
        anchor_term = -0.35 if contains_red else (0.15 if red_anchors else 0.0)
        score = (
            2.2 * abs(float(np.log(observed_ratio / expected_ratio)))
            + 2.5 * (1.0 - float(support_values.mean()))
            + 1.2 * (1.0 - dark_fraction)
            - 1.5 * area_ratio
            - 0.3 * line_coverage
            + anchor_term
        )
        candidates.append(
            BlackRectangle(
                corners=order_corners(corners),
                score=float(score),
                contains_white=contains_red,
                area_ratio=float(area_ratio),
            )
        )

    candidates.sort(key=lambda item: item.score)
    unique: list[BlackRectangle] = []
    for candidate in candidates:
        if any(
            quadrilateral_iou(candidate.corners, kept.corners) >= 0.72
            for kept in unique
        ):
            continue
        unique.append(candidate)
        if len(unique) >= 8:
            break

    # Validate the geometry using the competition markers after rectification.
    # A red electrical connector outside the factory can look like a red block
    # in image space and once caused a right-side crane/desk quadrilateral to
    # outrank the true boundary.  Physical 5 cm block dimensions in the warped
    # 60 x 30 cm plane provide a much stronger discriminator.  When no marker
    # is present, retain the geometry-only fallback for an empty factory state.
    marker_support: list[tuple[BlackRectangle, bool, bool]] = []
    for candidate in unique:
        has_heavy_block = False
        has_worker = False
        try:
            rectified, _homography = rectify_background(
                analysis_frame, candidate.corners, config
            )
            marker_measurements = measure_white_objects(rectified, config)
            has_heavy_block = any(
                item.kind == "heavy_block" for item in marker_measurements
            )
            has_worker = any(
                item.kind == "worker" for item in marker_measurements
            )
        except (ValueError, cv2.error):
            pass
        if has_heavy_block:
            candidate.score -= 0.80
        if has_worker:
            candidate.score -= 0.35
        # Retain this legacy field as an initial-reference validity flag.  A
        # physically plausible red block is stronger evidence than merely
        # enclosing any red pixel or electrical connector.
        candidate.contains_white = has_heavy_block
        marker_support.append((candidate, has_heavy_block, has_worker))

    both_markers = [
        candidate
        for candidate, has_heavy_block, has_worker in marker_support
        if has_heavy_block and has_worker
    ]
    heavy_marker = [
        candidate
        for candidate, has_heavy_block, _has_worker in marker_support
        if has_heavy_block
    ]
    if both_markers:
        unique = both_markers
    elif heavy_marker:
        unique = heavy_marker
    unique.sort(key=lambda item: item.score)
    for candidate in unique:
        candidate.corners = (
            candidate.corners / detection_scale
        ).astype(np.float32)
    return unique


def detect_black_rectangles(
    frame: np.ndarray,
    config: Config,
) -> list[BlackRectangle]:
    """Compatibility name for the current white factory-frame detector."""
    return detect_factory_rectangles(frame, config)


def detect_black_background(
    frame: np.ndarray,
    config: Config,
) -> np.ndarray | None:
    """Compatibility helper returning the best white factory boundary."""
    rectangles = detect_black_rectangles(frame, config)
    return None if not rectangles else rectangles[0].corners


def rectify_background(
    frame: np.ndarray,
    corners: np.ndarray,
    config: Config,
) -> tuple[np.ndarray, np.ndarray]:
    """Warp the reference rectangle to a centimeter-scaled top-down image."""
    corners = np.asarray(corners, dtype=np.float32).reshape(4, 2)
    edge_lengths = np.linalg.norm(
        np.roll(corners, -1, axis=0) - corners,
        axis=1,
    )
    if (
        not np.all(np.isfinite(corners))
        or not cv2.isContourConvex(corners)
        or abs(float(cv2.contourArea(corners))) < 100.0
        or float(edge_lengths.min()) < 5.0
    ):
        raise ValueError("Degenerate reference quadrilateral")

    top = np.linalg.norm(corners[1] - corners[0])
    bottom = np.linalg.norm(corners[2] - corners[3])
    left = np.linalg.norm(corners[3] - corners[0])
    right = np.linalg.norm(corners[2] - corners[1])
    horizontal_pixels = (top + bottom) / 2.0
    vertical_pixels = (left + right) / 2.0

    physical_long = max(config.background_width_cm, config.background_height_cm)
    physical_short = min(config.background_width_cm, config.background_height_cm)
    if horizontal_pixels >= vertical_pixels:
        physical_width = physical_long
        physical_height = physical_short
    else:
        physical_width = physical_short
        physical_height = physical_long

    output_width = max(2, round(physical_width * config.pixels_per_cm))
    output_height = max(2, round(physical_height * config.pixels_per_cm))
    destination = np.array(
        [
            [0, 0],
            [output_width - 1, 0],
            [output_width - 1, output_height - 1],
            [0, output_height - 1],
        ],
        dtype=np.float32,
    )
    homography = cv2.getPerspectiveTransform(corners, destination)
    if (
        not np.all(np.isfinite(homography))
        or np.linalg.cond(homography) > 1.0e12
    ):
        raise ValueError("Unstable reference homography")
    rectified = cv2.warpPerspective(
        frame, homography, (output_width, output_height)
    )
    return rectified, homography


def measure_white_objects(
    rectified: np.ndarray,
    config: Config,
) -> list[Measurement]:
    """Detect red 5 cm heavy blocks and yellow worker helmets."""
    object_blurred = cv2.GaussianBlur(rectified, (3, 3), 0)
    object_hsv = cv2.cvtColor(object_blurred, cv2.COLOR_BGR2HSV)
    red_mask = cv2.bitwise_or(
        cv2.inRange(
            object_hsv,
            np.array(
                (0, config.red_saturation_min, config.red_value_min),
                dtype=np.uint8,
            ),
            np.array((config.red_hue_low_max, 255, 255), dtype=np.uint8),
        ),
        cv2.inRange(
            object_hsv,
            np.array(
                (
                    config.red_hue_high_min,
                    config.red_saturation_min,
                    config.red_value_min,
                ),
                dtype=np.uint8,
            ),
            np.array((179, 255, 255), dtype=np.uint8),
        ),
    )
    yellow_hsv = object_hsv
    saturated_yellow_mask = cv2.inRange(
        yellow_hsv,
        np.array(
            (
                config.yellow_hue_min,
                config.yellow_saturation_min,
                config.yellow_value_min,
            ),
            dtype=np.uint8,
        ),
        np.array((config.yellow_hue_max, 255, 255), dtype=np.uint8),
    )
    # Two helmet markers in the calibrated camera are partially blown out:
    # their yellow core becomes almost white (very low saturation).  Include
    # these highlights, then let physical diameter, shape, local contrast and
    # temporal confirmation reject the large white paper and random glare.
    overexposed_helmet_mask = cv2.inRange(
        yellow_hsv,
        np.array(
            (0, 0, config.helmet_overexposed_value_min), dtype=np.uint8
        ),
        np.array(
            (179, config.helmet_overexposed_saturation_max, 255),
            dtype=np.uint8,
        ),
    )
    yellow_mask = cv2.bitwise_or(
        saturated_yellow_mask, overexposed_helmet_mask
    )

    block_open_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    block_close_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    red_mask = cv2.morphologyEx(
        red_mask, cv2.MORPH_OPEN, block_open_kernel
    )
    red_mask = cv2.morphologyEx(
        red_mask, cv2.MORPH_CLOSE, block_close_kernel
    )
    helmet_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    yellow_mask = cv2.morphologyEx(
        yellow_mask, cv2.MORPH_OPEN, helmet_kernel
    )
    yellow_mask = cv2.morphologyEx(
        yellow_mask, cv2.MORPH_CLOSE, helmet_kernel
    )

    # A heavy block is allowed to approach the factory boundary, while the
    # yellow helmet mask needs a wider guard band to reject the yellow points
    # on the surrounding light strip.  Sharing the old 2.5 cm rim caused the
    # 5 cm red block to disappear as soon as its centre approached an edge.
    red_border = max(2, round(config.pixels_per_cm * 0.5))
    yellow_border = max(3, round(config.pixels_per_cm * 2.5))
    red_mask[:red_border, :] = 0
    red_mask[-red_border:, :] = 0
    red_mask[:, :red_border] = 0
    red_mask[:, -red_border:] = 0
    yellow_mask[:yellow_border, :] = 0
    yellow_mask[-yellow_border:, :] = 0
    yellow_mask[:, :yellow_border] = 0
    yellow_mask[:, -yellow_border:] = 0

    red_contours, _ = cv2.findContours(
        red_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    yellow_contours, _ = cv2.findContours(
        yellow_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    block_min_area_px = (
        0.45
        * config.heavy_block_min_side_cm**2
        * config.pixels_per_cm**2
    )
    max_area_px = rectified.shape[0] * rectified.shape[1] * 0.85
    measurements: list[Measurement] = []

    for contour in red_contours:
        area = cv2.contourArea(contour)
        if not block_min_area_px <= area <= max_area_px:
            continue

        rotated_rectangle = cv2.minAreaRect(contour)
        side_a, side_b = rotated_rectangle[1]
        if side_a < 2 or side_b < 2:
            continue
        length_cm = max(side_a, side_b) / config.pixels_per_cm
        width_cm = min(side_a, side_b) / config.pixels_per_cm
        rectangle_area = side_a * side_b
        rectangle_fill_ratio = area / rectangle_area
        side_ratio = width_cm / max(length_cm, 1.0e-6)
        if not (
            config.heavy_block_min_side_cm
            <= width_cm
            <= length_cm
            <= config.heavy_block_max_side_cm
            and rectangle_fill_ratio >= config.heavy_block_min_fill_ratio
            and side_ratio >= config.heavy_block_min_side_ratio
        ):
            continue
        box = cv2.boxPoints(rotated_rectangle).astype(np.float32)
        measurements.append(
            Measurement(
                box=box,
                length_cm=length_cm,
                width_cm=width_cm,
                area_px=area,
                kind="heavy_block",
            )
        )

    value_channel = yellow_hsv[:, :, 2]
    minimum_yellow_area_px = max(
        5.0,
        0.35
        * np.pi
        * (0.5 * config.worker_min_diameter_cm * config.pixels_per_cm) ** 2,
    )
    for contour in yellow_contours:
        area = cv2.contourArea(contour)
        if not minimum_yellow_area_px <= area <= max_area_px:
            continue

        perimeter = cv2.arcLength(contour, True)
        if perimeter <= 0:
            continue
        circularity = 4.0 * np.pi * area / (perimeter * perimeter)
        rotated_rectangle = cv2.minAreaRect(contour)
        side_a, side_b = rotated_rectangle[1]
        if min(side_a, side_b) < 2:
            continue
        side_ratio = min(side_a, side_b) / max(side_a, side_b)
        circle_center, circle_radius = cv2.minEnclosingCircle(contour)
        enclosing_circle_area = np.pi * circle_radius * circle_radius
        circle_fill_ratio = (
            area / enclosing_circle_area if enclosing_circle_area > 0 else 0.0
        )
        diameter_cm = 2.0 * circle_radius / config.pixels_per_cm
        if not (
            config.worker_min_diameter_cm
            <= diameter_cm
            <= config.worker_max_diameter_cm
            and circularity >= config.worker_min_circularity
            and circle_fill_ratio >= config.worker_min_circle_fill
            and side_ratio >= config.worker_min_side_ratio
        ):
            continue

        # Yellow alone is insufficient: require the bright helmet marker to
        # stand out from a surrounding annulus.  This rejects yellowish floor
        # texture and illumination gradients while retaining slightly washed
        # out helmet edges.
        x, y, width, height = cv2.boundingRect(contour)
        ring_width = max(2, round(circle_radius * 0.65))
        x0 = max(0, x - ring_width)
        y0 = max(0, y - ring_width)
        x1 = min(rectified.shape[1], x + width + ring_width)
        y1 = min(rectified.shape[0], y + height + ring_width)
        local_contour = contour.copy()
        local_contour[:, 0, 0] -= x0
        local_contour[:, 0, 1] -= y0
        object_mask = np.zeros((y1 - y0, x1 - x0), dtype=np.uint8)
        cv2.drawContours(object_mask, [local_contour], -1, 255, cv2.FILLED)
        dilation_size = 2 * ring_width + 1
        dilation_kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (dilation_size, dilation_size)
        )
        surrounding_mask = cv2.dilate(object_mask, dilation_kernel)
        surrounding_mask[object_mask > 0] = 0
        local_value = value_channel[y0:y1, x0:x1]
        object_values = local_value[object_mask > 0]
        surrounding_values = local_value[surrounding_mask > 0]
        if object_values.size == 0 or surrounding_values.size == 0:
            continue
        yellow_fraction = float(
            np.mean(
                saturated_yellow_mask[y0:y1, x0:x1][object_mask > 0] > 0
            )
        )
        if yellow_fraction < config.worker_min_yellow_fraction:
            continue
        if float(np.median(surrounding_values)) > config.worker_max_surrounding_value:
            continue
        value_contrast = float(
            np.median(object_values) - np.median(surrounding_values)
        )
        if value_contrast < config.worker_min_value_contrast:
            continue

        box = cv2.boxPoints(rotated_rectangle).astype(np.float32)
        measurements.append(
            Measurement(
                box=box,
                length_cm=diameter_cm,
                width_cm=diameter_cm,
                area_px=area,
                kind="worker",
                circle_center=np.asarray(circle_center, dtype=np.float32),
                circle_radius_px=float(circle_radius),
            )
        )

    measurements.sort(key=lambda item: item.area_px, reverse=True)
    return measurements


def draw_measurements(
    frame: np.ndarray,
    config: Config,
    tracker: ReferenceTracker | None = None,
) -> np.ndarray:
    """Draw the factory boundary, red heavy blocks, and yellow workers."""
    global LAST_MEASUREMENTS
    LAST_MEASUREMENTS = []
    result = frame.copy()
    text_labels: list[
        tuple[str, tuple[int, int], tuple[int, int, int], int]
    ] = []
    if tracker is None:
        detected_rectangles = detect_black_rectangles(frame, config)
        corners = (
            None if not detected_rectangles else detected_rectangles[0].corners
        )
    else:
        corners = tracker.update(frame, config)
    if corners is None:
        cv2.putText(
            result,
            "White factory boundary not found",
            (20, 42),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (0, 0, 255),
            3,
            cv2.LINE_AA,
        )
        return result

    try:
        rectified, homography = rectify_background(frame, corners, config)
        inverse_homography = np.linalg.inv(homography)
    except (ValueError, np.linalg.LinAlgError, cv2.error) as error:
        # A threshold sweep can very occasionally produce a nearly collinear
        # quadrilateral.  Do not let a Tk callback die and freeze both live
        # windows; discard it and force an immediate reference search.
        if tracker is not None:
            tracker.reset_reference()
        cv2.putText(
            result,
            "Invalid reference geometry - retrying",
            (20, 42),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (0, 0, 255),
            3,
            cv2.LINE_AA,
        )
        LOGGER.warning("Reference geometry rejected: %s", error)
        return result

    measurements = measure_white_objects(rectified, config)
    if tracker is not None:
        measurements = tracker.worker_stabilizer.update(measurements, config)
    LAST_MEASUREMENTS = list(measurements)

    cv2.polylines(
        result,
        [np.rint(corners).astype(np.int32)],
        True,
        (255, 120, 0),
        3,
        cv2.LINE_AA,
    )
    main_corners_int = np.rint(corners).astype(np.int32)
    floor_label_x = int(
        np.clip(main_corners_int[:, 0].min() + 12, 5, frame.shape[1] - 320)
    )
    floor_top = int(main_corners_int[:, 1].min())
    floor_label_y = floor_top + 10
    floor_label_y = int(np.clip(floor_label_y, 5, frame.shape[0] - 38))
    text_labels.append(
        (
            f"Factory area: {config.background_width_cm:g} x "
            f"{config.background_height_cm:g} cm",
            (floor_label_x, floor_label_y),
            (255, 120, 0),
            30,
        )
    )

    heavy_block_count = 0
    worker_count = 0
    worker_label_rectangles: list[tuple[int, int, int, int]] = []

    def place_worker_label(
        text: str,
        source_circle: np.ndarray,
        size: int,
    ) -> tuple[int, int]:
        """Place compact worker labels without covering another worker label."""
        scale = size / 32.0
        (text_width, text_height), _ = cv2.getTextSize(
            text, cv2.FONT_HERSHEY_SIMPLEX, scale, 2
        )
        center_x = float(source_circle[:, 0].mean())
        center_y = float(source_circle[:, 1].mean())
        minimum_x = float(source_circle[:, 0].min())
        maximum_x = float(source_circle[:, 0].max())
        minimum_y = float(source_circle[:, 1].min())
        maximum_y = float(source_circle[:, 1].max())
        candidates = [
            (maximum_x + 5, center_y - size / 2),
            (minimum_x - text_width - 5, center_y - size / 2),
            (maximum_x + 5, center_y + 5),
            (minimum_x - text_width - 5, center_y + 5),
            (center_x - text_width / 2, minimum_y - size - 5),
            (center_x - text_width / 2, maximum_y + 5),
        ]

        best_position = (5, 5)
        best_overlap = float("inf")
        for candidate_x, candidate_y in candidates:
            x = int(
                np.clip(
                    candidate_x,
                    5,
                    max(5, frame.shape[1] - text_width - 5),
                )
            )
            y = int(
                np.clip(candidate_y, 5, max(5, frame.shape[0] - size - 5))
            )
            rectangle = (x, y, x + text_width, y + max(size, text_height))
            overlap = 0
            for occupied in worker_label_rectangles:
                overlap_width = max(
                    0,
                    min(rectangle[2], occupied[2])
                    - max(rectangle[0], occupied[0]),
                )
                overlap_height = max(
                    0,
                    min(rectangle[3], occupied[3])
                    - max(rectangle[1], occupied[1]),
                )
                overlap += overlap_width * overlap_height
            if overlap < best_overlap:
                best_overlap = overlap
                best_position = (x, y)
                if overlap == 0:
                    worker_label_rectangles.append(rectangle)
                    return best_position

        x, y = best_position
        worker_label_rectangles.append(
            (x, y, x + text_width, y + max(size, text_height))
        )
        return best_position

    for measurement in measurements:
        source_box = cv2.perspectiveTransform(
            measurement.box.reshape(1, 4, 2), inverse_homography
        ).reshape(4, 2)
        label_x = int(np.clip(source_box[:, 0].min(), 5, frame.shape[1] - 5))
        label_y = int(np.clip(source_box[:, 1].min() - 34, 8, frame.shape[0] - 32))

        if measurement.kind == "worker" and measurement.circle_center is not None:
            worker_count += 1
            display_worker_id = (
                measurement.worker_id
                if measurement.worker_id is not None
                else worker_count
            )
            angles = np.linspace(0.0, 2.0 * np.pi, 48, endpoint=False)
            circle_points = np.column_stack(
                (
                    measurement.circle_center[0]
                    + measurement.circle_radius_px * np.cos(angles),
                    measurement.circle_center[1]
                    + measurement.circle_radius_px * np.sin(angles),
                )
            ).astype(np.float32)
            source_circle = cv2.perspectiveTransform(
                circle_points.reshape(1, -1, 2), inverse_homography
            ).reshape(-1, 2)
            cv2.polylines(
                result,
                [np.rint(source_circle).astype(np.int32)],
                True,
                (0, 255, 255),
                4,
                cv2.LINE_AA,
            )
            diameter_cm = (
                2.0 * measurement.circle_radius_px / config.pixels_per_cm
            )
            worker_label = f"W{display_worker_id} D={diameter_cm:.1f}cm"
            label_x, label_y = place_worker_label(
                worker_label, source_circle, 18
            )
            text_labels.append(
                (
                    worker_label,
                    (label_x, label_y),
                    (0, 255, 255),
                    18,
                )
            )
        elif measurement.kind in ("heavy_block", "lifted_object"):
            heavy_block_count += 1
            display_block_id = (
                measurement.worker_id
                if measurement.worker_id is not None
                else heavy_block_count
            )
            cv2.polylines(
                result,
                [np.rint(source_box).astype(np.int32)],
                True,
                (0, 0, 255),
                4,
                cv2.LINE_AA,
            )
            text_labels.append(
                (
                    f"Heavy block {display_block_id}: "
                    f"L={measurement.length_cm:.1f} cm  "
                    f"W={measurement.width_cm:.1f} cm",
                    (label_x, label_y),
                    (0, 0, 255),
                    26,
                )
            )
    text_labels.extend(
        [
            (
                f"Heavy blocks: {heavy_block_count}",
                (20, 10),
                (0, 0, 255),
                26,
            ),
            (
                f"Workers: {worker_count}",
                (20, 44),
                (0, 255, 255),
                26,
            ),
        ]
    )
    return draw_text_labels(result, text_labels)


def open_camera(args: argparse.Namespace) -> cv2.VideoCapture:
    """Open the UVC camera using its tested MJPEG mode."""
    if args.device.isdigit():
        device: str | int = int(args.device)
    else:
        # OpenCV 4.9's V4L2 backend on the Orange Pi rejects some /dev/v4l
        # symlink names even though they point to a valid video node.  Resolve
        # them to /dev/videoN before opening the camera.
        device = os.path.realpath(args.device)
    camera = cv2.VideoCapture(device, cv2.CAP_V4L2)
    if not camera.isOpened():
        raise RuntimeError(
            f"Cannot open camera: {args.device} (resolved to {device}). "
            "It may already be in use; check with: "
            "pgrep -af white_object_detector.py"
        )
    camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, args.frame_width)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, args.frame_height)
    camera.set(cv2.CAP_PROP_FPS, args.frame_rate)
    camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    # The green crane LEDs use PWM.  Aperture-priority auto exposure can lock
    # onto a bright PWM phase and make the white boundary/red block nearly
    # black on the next camera start.  V4L2 mode 1 is manual exposure.
    requested_exposure = float(
        getattr(args, "exposure", DEFAULT_CAMERA_EXPOSURE)
    )
    manual_mode_set = camera.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1.0)
    exposure_set = camera.set(cv2.CAP_PROP_EXPOSURE, requested_exposure)
    LOGGER.info(
        "CAMERA exposure manual_set=%s exposure_set=%s requested=%.0f "
        "actual_mode=%.0f actual_exposure=%.0f",
        manual_mode_set,
        exposure_set,
        requested_exposure,
        camera.get(cv2.CAP_PROP_AUTO_EXPOSURE),
        camera.get(cv2.CAP_PROP_EXPOSURE),
    )
    return camera


def opencv_gui_available() -> bool:
    """Return whether this OpenCV build includes a HighGUI window backend."""
    for line in cv2.getBuildInformation().splitlines():
        if line.strip().startswith("GUI:"):
            return line.split(":", 1)[1].strip().upper() != "NONE"
    return False


def run_opencv_windows(
    camera: cv2.VideoCapture,
    config: Config,
    tracker: ReferenceTracker,
    target_fps: int,
) -> None:
    """Display the two streams with OpenCV HighGUI."""
    cv2.namedWindow("Original", cv2.WINDOW_NORMAL)
    cv2.namedWindow("Factory Object Detection", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Original", 900, 506)
    cv2.resizeWindow("Factory Object Detection", 900, 506)
    cv2.moveWindow("Original", 20, 60)
    cv2.moveWindow("Factory Object Detection", 960, 60)
    LOGGER.info("Press Q or Esc in either window to quit.")
    target_period = 1.0 / max(1, target_fps)
    performance = PerformanceLogger("opencv")

    while True:
        frame_started = time.perf_counter()
        ok, frame = camera.read()
        if not ok:
            raise RuntimeError("Camera read failed")
        capture_finished = time.perf_counter()

        measurement_result = draw_measurements(frame, config, tracker)
        process_finished = time.perf_counter()
        cv2.imshow("Original", frame)
        cv2.imshow("Factory Object Detection", measurement_result)
        display_finished = time.perf_counter()

        performance.record(
            (capture_finished - frame_started) * 1000.0,
            (process_finished - capture_finished) * 1000.0,
            (display_finished - process_finished) * 1000.0,
            (display_finished - frame_started) * 1000.0,
            tracker,
        )

        elapsed = display_finished - frame_started
        wait_ms = max(1, round((target_period - elapsed) * 1000))
        key = cv2.waitKey(wait_ms) & 0xFF
        if key in (ord("q"), ord("Q"), 27):
            break


def run_tkinter_windows(
    camera: cv2.VideoCapture,
    config: Config,
    tracker: ReferenceTracker,
    target_fps: int,
) -> None:
    """Display two streams when OpenCV was built without a GUI backend."""
    # SSH shells normally have no DISPLAY variable even when the Orange Pi's
    # local desktop is running.  Reuse that local X11 display automatically so
    # `python3 white_object_detector.py` works without a DISPLAY prefix.
    if not os.environ.get("DISPLAY") and os.path.exists("/tmp/.X11-unix/X0"):
        os.environ["DISPLAY"] = ":0"
        LOGGER.info("DISPLAY was unset; using the local desktop at :0.")

    import tkinter as tk

    from PIL import Image, ImageTk

    try:
        root = tk.Tk()
    except tk.TclError as error:
        raise RuntimeError(
            "Cannot open a display window. From SSH, run with DISPLAY=:0 "
            "or start the program in the Orange Pi desktop terminal."
        ) from error
    root.title("Original")
    result_window = tk.Toplevel(root)
    result_window.title("Factory Object Detection")
    original_label = tk.Label(root)
    result_label = tk.Label(result_window)
    original_label.pack()
    result_label.pack()
    running = True

    # Put the two previews next to each other instead of allowing the window
    # manager to create both at the same position.  On a smaller desktop,
    # reduce only the preview size; detection still uses the full camera frame.
    screen_width = root.winfo_screenwidth()
    horizontal_margin = 20
    window_gap = 30
    top_margin = 60
    available_per_window = (
        screen_width - 2 * horizontal_margin - window_gap
    ) // 2
    display_width = max(320, min(640, available_per_window))
    original_x = horizontal_margin
    result_x = horizontal_margin + display_width + window_gap
    root.geometry(f"+{original_x}+{top_margin}")
    result_window.geometry(f"+{result_x}+{top_margin}")
    target_period = 1.0 / max(1, target_fps)
    performance = PerformanceLogger("tkinter")

    def close_windows(_event: object | None = None) -> None:
        nonlocal running
        if not running:
            return
        running = False
        root.quit()

    def to_photo(frame: np.ndarray) -> ImageTk.PhotoImage:
        height, width = frame.shape[:2]
        scale = min(1.0, display_width / width)
        if scale < 1.0:
            frame = cv2.resize(
                frame,
                (round(width * scale), round(height * scale)),
                interpolation=cv2.INTER_AREA,
            )
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return ImageTk.PhotoImage(Image.fromarray(rgb))

    def update_frames() -> None:
        if not running:
            return
        frame_started = time.perf_counter()
        ok, frame = camera.read()
        if not ok:
            LOGGER.error("Camera read failed")
            close_windows()
            return

        capture_finished = time.perf_counter()
        measurement_result = draw_measurements(frame, config, tracker)
        process_finished = time.perf_counter()
        original_photo = to_photo(frame)
        result_photo = to_photo(measurement_result)
        original_label.configure(image=original_photo)
        result_label.configure(image=result_photo)
        # Tk images must be retained while the labels are displaying them.
        original_label.image = original_photo
        result_label.image = result_photo
        display_finished = time.perf_counter()
        performance.record(
            (capture_finished - frame_started) * 1000.0,
            (process_finished - capture_finished) * 1000.0,
            (display_finished - process_finished) * 1000.0,
            (display_finished - frame_started) * 1000.0,
            tracker,
        )
        elapsed = display_finished - frame_started
        wait_ms = max(1, round((target_period - elapsed) * 1000))
        root.after(wait_ms, update_frames)

    root.protocol("WM_DELETE_WINDOW", close_windows)
    result_window.protocol("WM_DELETE_WINDOW", close_windows)
    root.bind("<KeyPress-q>", close_windows)
    root.bind("<KeyPress-Q>", close_windows)
    root.bind("<Escape>", close_windows)
    result_window.bind("<KeyPress-q>", close_windows)
    result_window.bind("<KeyPress-Q>", close_windows)
    result_window.bind("<Escape>", close_windows)
    LOGGER.info(
        "OpenCV GUI unavailable; using Tkinter. Press Q or Esc to quit."
    )
    root.after(0, update_frames)
    root.mainloop()
    try:
        root.destroy()
    except tk.TclError:
        pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", default=DEFAULT_CAMERA_DEVICE)
    # These defaults are the tested real-time settings for the Orange Pi.
    parser.add_argument("--frame-width", type=int, default=1280)
    parser.add_argument("--frame-height", type=int, default=720)
    parser.add_argument("--frame-rate", type=int, default=20)
    parser.add_argument(
        "--exposure",
        type=float,
        default=DEFAULT_CAMERA_EXPOSURE,
        help="Manual V4L2 exposure in 0.1 ms units (default: 90)",
    )
    parser.add_argument(
        "--background-width-cm",
        type=float,
        default=DEFAULT_BACKGROUND_WIDTH_CM,
    )
    parser.add_argument(
        "--background-height-cm",
        type=float,
        default=DEFAULT_BACKGROUND_HEIGHT_CM,
    )
    parser.add_argument("--black-value-max", type=int, default=120)
    parser.add_argument("--white-value-min", type=int, default=175)
    parser.add_argument("--white-saturation-max", type=int, default=60)
    parser.add_argument("--min-object-area-cm2", type=float, default=1.0)
    parser.add_argument("--reference-white-value-min", type=int, default=150)
    parser.add_argument(
        "--reference-white-saturation-max", type=int, default=85
    )
    parser.add_argument("--reference-min-area-ratio", type=float, default=0.14)
    parser.add_argument("--reference-max-area-ratio", type=float, default=0.35)
    parser.add_argument("--red-hue-low-max", type=int, default=12)
    parser.add_argument("--red-hue-high-min", type=int, default=168)
    parser.add_argument("--red-saturation-min", type=int, default=70)
    parser.add_argument("--red-value-min", type=int, default=70)
    parser.add_argument("--heavy-block-min-side-cm", type=float, default=3.5)
    parser.add_argument("--heavy-block-max-side-cm", type=float, default=6.8)
    parser.add_argument("--heavy-block-min-fill-ratio", type=float, default=0.68)
    parser.add_argument("--heavy-block-min-side-ratio", type=float, default=0.68)
    parser.add_argument("--yellow-hue-min", type=int, default=18)
    parser.add_argument("--yellow-hue-max", type=int, default=42)
    parser.add_argument("--yellow-saturation-min", type=int, default=30)
    parser.add_argument("--yellow-value-min", type=int, default=130)
    parser.add_argument(
        "--helmet-overexposed-saturation-max", type=int, default=65
    )
    parser.add_argument(
        "--helmet-overexposed-value-min", type=int, default=150
    )
    parser.add_argument("--worker-min-diameter-cm", type=float, default=0.7)
    parser.add_argument("--worker-max-diameter-cm", type=float, default=4.0)
    parser.add_argument("--worker-confirmation-frames", type=int, default=2)
    parser.add_argument("--worker-max-missed-frames", type=int, default=4)
    parser.add_argument(
        "--reference-search-interval",
        type=int,
        default=1800,
        help="Frames between full factory-boundary searches (default: 1800)",
    )
    parser.add_argument(
        "--log-file",
        default="detector.log",
        help="Performance/error log path; use an empty string to disable",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_logging(args.log_file)
    cv2.setUseOptimized(True)
    cv2.setNumThreads(max(1, min(2, cv2.getNumberOfCPUs())))
    if args.background_width_cm <= 0 or args.background_height_cm <= 0:
        raise ValueError("Background dimensions must be positive")
    if args.exposure <= 0:
        raise ValueError("Camera exposure must be positive")
    if not 0 <= args.yellow_hue_min <= args.yellow_hue_max <= 179:
        raise ValueError("Yellow hue range must satisfy 0 <= min <= max <= 179")
    if not 0 <= args.red_hue_low_max < args.red_hue_high_min <= 179:
        raise ValueError(
            "Red hue bounds must satisfy 0 <= low max < high min <= 179"
        )
    byte_parameters = {
        "yellow saturation minimum": args.yellow_saturation_min,
        "yellow value minimum": args.yellow_value_min,
        "overexposed saturation maximum": (
            args.helmet_overexposed_saturation_max
        ),
        "overexposed value minimum": args.helmet_overexposed_value_min,
        "reference white value minimum": args.reference_white_value_min,
        "reference white saturation maximum": (
            args.reference_white_saturation_max
        ),
        "red saturation minimum": args.red_saturation_min,
        "red value minimum": args.red_value_min,
    }
    for parameter_name, parameter_value in byte_parameters.items():
        if not 0 <= parameter_value <= 255:
            raise ValueError(f"{parameter_name} must be between 0 and 255")
    if not 0 < args.worker_min_diameter_cm < args.worker_max_diameter_cm:
        raise ValueError("Worker diameter range must be positive and increasing")
    if not (
        0.0
        < args.reference_min_area_ratio
        < args.reference_max_area_ratio
        < 1.0
    ):
        raise ValueError(
            "Reference area ratios must be increasing and between 0 and 1"
        )
    if not 0 < args.heavy_block_min_side_cm < args.heavy_block_max_side_cm:
        raise ValueError(
            "Heavy-block side range must be positive and increasing"
        )
    for parameter_name, parameter_value in {
        "heavy-block fill ratio": args.heavy_block_min_fill_ratio,
        "heavy-block side ratio": args.heavy_block_min_side_ratio,
    }.items():
        if not 0.0 < parameter_value <= 1.0:
            raise ValueError(f"{parameter_name} must be in (0, 1]")
    if args.worker_confirmation_frames <= 0:
        raise ValueError("Worker confirmation frames must be positive")
    if args.worker_max_missed_frames < 0:
        raise ValueError("Worker maximum missed frames cannot be negative")
    config = Config(
        background_width_cm=args.background_width_cm,
        background_height_cm=args.background_height_cm,
        black_value_max=args.black_value_max,
        white_value_min=args.white_value_min,
        white_saturation_max=args.white_saturation_max,
        min_object_area_cm2=args.min_object_area_cm2,
        reference_white_value_min=args.reference_white_value_min,
        reference_white_saturation_max=(
            args.reference_white_saturation_max
        ),
        reference_min_area_ratio=args.reference_min_area_ratio,
        reference_max_area_ratio=args.reference_max_area_ratio,
        red_hue_low_max=args.red_hue_low_max,
        red_hue_high_min=args.red_hue_high_min,
        red_saturation_min=args.red_saturation_min,
        red_value_min=args.red_value_min,
        heavy_block_min_side_cm=args.heavy_block_min_side_cm,
        heavy_block_max_side_cm=args.heavy_block_max_side_cm,
        heavy_block_min_fill_ratio=args.heavy_block_min_fill_ratio,
        heavy_block_min_side_ratio=args.heavy_block_min_side_ratio,
        yellow_hue_min=args.yellow_hue_min,
        yellow_hue_max=args.yellow_hue_max,
        yellow_saturation_min=args.yellow_saturation_min,
        yellow_value_min=args.yellow_value_min,
        helmet_overexposed_saturation_max=(
            args.helmet_overexposed_saturation_max
        ),
        helmet_overexposed_value_min=args.helmet_overexposed_value_min,
        worker_min_diameter_cm=args.worker_min_diameter_cm,
        worker_max_diameter_cm=args.worker_max_diameter_cm,
        worker_confirmation_frames=args.worker_confirmation_frames,
        worker_max_missed_frames=args.worker_max_missed_frames,
    )

    if args.reference_search_interval <= 0:
        raise ValueError("Reference search interval must be positive")
    LOGGER.info(
        "START device=%s resolution=%dx%d target_fps=%d reference=%gx%g_cm "
        "reference_search_interval=%d opencv_threads=%d "
        "boundary_white=V%d+_S%d- area_ratio=%.2f-%.2f "
        "red_hsv=H0-%d_or_%d-179_S%d+_V%d+ block_side_cm=%.1f-%.1f "
        "helmet_hsv=H%d-%d_S%d+_V%d+ overexposed=S%d-_V%d+ "
        "helmet_diameter_cm=%.1f-%.1f confirm_frames=%d max_missed=%d",
        args.device,
        args.frame_width,
        args.frame_height,
        args.frame_rate,
        args.background_width_cm,
        args.background_height_cm,
        args.reference_search_interval,
        cv2.getNumThreads(),
        args.reference_white_value_min,
        args.reference_white_saturation_max,
        args.reference_min_area_ratio,
        args.reference_max_area_ratio,
        args.red_hue_low_max,
        args.red_hue_high_min,
        args.red_saturation_min,
        args.red_value_min,
        args.heavy_block_min_side_cm,
        args.heavy_block_max_side_cm,
        args.yellow_hue_min,
        args.yellow_hue_max,
        args.yellow_saturation_min,
        args.yellow_value_min,
        args.helmet_overexposed_saturation_max,
        args.helmet_overexposed_value_min,
        args.worker_min_diameter_cm,
        args.worker_max_diameter_cm,
        args.worker_confirmation_frames,
        args.worker_max_missed_frames,
    )

    camera = open_camera(args)
    tracker = ReferenceTracker(search_interval=args.reference_search_interval)
    for _ in range(30):
        ok, _ = camera.read()
        if not ok:
            camera.release()
            raise RuntimeError("Camera warm-up failed")

    try:
        if opencv_gui_available():
            run_opencv_windows(camera, config, tracker, args.frame_rate)
        else:
            run_tkinter_windows(camera, config, tracker, args.frame_rate)
    finally:
        camera.release()
        tracker.close()
        if opencv_gui_available():
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
