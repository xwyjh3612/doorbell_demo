# 语音对讲呼叫提示音

ESP32 的呼入和呼出使用不同的电话提示音，均为本项目通过正弦波合成的原创素材，没有使用下载歌曲或第三方铃声。

| 用途 | 文件 | 声音与节奏 |
| --- | --- | --- |
| 呼入 | `ring.aac` | 中频电话双响：主音 660Hz，搭配 990Hz 和 1320Hz，每两秒一组 |
| 呼出 | `outgoing.aac` | 450Hz 长回铃，带 900Hz 泛音，响 1 秒、停 3 秒 |
| 联网 | `join.aac` | 中文语音“联网成功”，播放一次 |

两者为 16kHz 单声道 AAC-LC/ADTS，淡入 25ms、淡出 65ms。保留原来的 4 秒周期和接听、挂断时的停止逻辑。总输出为 95/100；本地 AAC 提示音直接播放。通话时只增强解码后的对端单声道人声，轻声最多提高约 18dB，峰值仍限制在约 −2dBFS。处理复用当前解码帧，不新增音频队列。

`DOOR_BELL_TONE_RING` 保留原枚举值，作为呼入提示音的历史别名；`DOOR_BELL_TONE_JOIN_SUCCESS` 保留原值，作为联网提示音的历史别名。联网提示在 MQTT 已连接后通过本地通话控制队列播放，尚未联网时不播放，呼叫或升级期间不打断当前音频。其他提示音保持现有素材。安卓 App 收到设备来电时仍使用手机系统铃声。

重新生成素材：

```powershell
python tools/generate-call-tones.py --ffmpeg F:/ffmpeg/bin/ffmpeg.exe
```

生成的 AAC 和校验清单位于 `main/`，可试听的 WAV 位于本地 `build/call-tones/incoming.wav` 与 `outgoing.wav`。FFmpeg 版本可能影响编码结果，以当次 `call-tones.json` 的 SHA256 为准。

仅更新呼入素材可追加 `--only incoming`，保留呼出音频文件。

联网语音使用 Windows 内置中文语音生成，可重新运行 `./tools/generate-network-prompt.ps1`。试听文件为 `build/call-tones/network-success.wav`，校验清单为 `main/network-prompt.json`。
