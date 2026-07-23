# AirPods 环境音频分析与串口发送设计

## 目标

AirPods Pro 只负责采集环境声音，不播放警告音。程序每 4.5 秒开始一轮，使用 HFP 麦克风采集并保存精确 0.8 秒音频，调用 RBCC_Noise 模型选择 2000–5000 Hz 范围内的一个最佳频率，再由 GUI 通过 `/dev/ttyUSB0` 发送 UTF-8 `beep:XXXX`。

## 固定配置

- 蓝牙卡：`bluez_card.28_2D_7F_E7_2F_8F`
- 配置：`handsfree_head_unit`，mSBC，16 kHz 单声道输入
- 环境录音：`/home/HwHiAiUser/Desktop/RBCC/RBCC_Interface/runtime/environment_audio/latest.wav`
- 录音长度：0.8 秒、16 kHz、单声道 PCM WAV，每轮覆盖
- 更新间隔：4.5 秒起始到起始
- 最佳频率：一个四位整数，闭区间 2000–5000 Hz
- 串口：115200 8N1，UTF-8 `beep:XXXX`，精确 9 字节，无回车换行

## 数据流

1. worker 确保 AirPods 使用 HFP，并发现 `bluez_source.*` 麦克风源。
2. ffmpeg 采集 0.8 秒；边界不足的少量样本补零、超出的样本裁剪，固定保存 12800 个样本。
3. `load_wav()` 读取文件，`analyze_noise()` 分析，`select_warning_frequencies()` 选择一个最佳频率。
4. worker 输出包含 `best_alarm_hz` 的 JSON `ok` 事件。
5. GUI 校验频率有限且位于 2000–5000，将其格式化为 `beep:XXXX`，编码为 UTF-8，完整写入并 flush 串口。
6. AirPods 不执行任何警告音生成或播放。

## 错误处理与验证

设备断开、录音失败或串口异常时不中止循环，界面显示状态并在后续周期重试。按用户要求不创建源代码备份、不运行全量测试，只做语法检查和一次真实采集、模型分析、串口实发检查。
