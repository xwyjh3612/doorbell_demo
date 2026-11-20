# 2026-11-20 连续通话验收

本轮同一次 App ↔ 实物 ESP32 通话持续观察 1800 秒，通过脚本验收。19:06:26.007251 接通，最后一条双向统计为 19:36:27.978688，结果在 19:36:32 写完；时区为 UTC+8。所有更早的失败均保留在[排查记录](../通话中断与4G供电排查.md)，没有累计多次通话时长。

## 固件与条件

- 应用：`outputs/firmware/voice-radar60.bin`，2,782,944 字节，SHA-256 `5ebad5ab81b6c7822e5a72e85002e98e87fbb947847c62b16f1700aba59ac085`。
- 刷写审计：`build/voice-radar-flash-20261120-182421/device.json`；归档镜像与上述 SHA 一致。本轮没有重新构建或刷写，结束仍保留该应用。
- 对端：实物 ESP32-S3 / ML307R-DL；呼叫端为 Android 10 模拟器中的原生语音对讲 App 0.5，经过外网 `voice.2811.top`，设备 MQTT、App WSS、WebRTC 音频。
- 用户报告 ML307 使用手机充电器供电；本轮未更换电源或线材。5V 档额定电流、是否与功放共用、板上稳压芯片及瞬态电压尚未确认。
- 可选 60GHz 雷达代码包含在固件内；雷达电源沿用用户此前拔掉的状态。本轮 UART 没有有效雷达帧，不将此结果作为雷达联合供电验收。
- 保留只有一个待收 UDP 包的实现，新包覆盖旧包；本轮不注入重复 ICE、不执行任务栈扫描 `i`。

## 结果

| 检查项 | 结果 |
| --- | --- |
| 脚本 `passed` / 目标观察时间 | true / 1800 秒 |
| 音频统计 / 同时有发送和接收字节的统计 | 901 / 901 |
| 相邻音频统计最大间隔 | 2.024464 秒 |
| AFE 缓冲区满告警 | 0 |
| `AT_DIAG` 超时/错误记录 | 0 |
| `AT_RX_DIAG` 错误诊断记录 | 0 |
| `MATREADY` 模组启动通知 | 0 |
| 观察期设备断开、栈溢出、崩溃 | 未观察到，脚本通过 |
| 结束时原生 App UI | 保持“通话中”，随后测试主动挂断 |
| 挂断清理 | 19:36:33 UDP 对象正常销毁；恢复采集后未见新增崩溃、AFE 或 AT 错误 |

统计间隔反映日志输出频率，不是声音传输延迟。本轮证明这些测试条件下的双向包收发连续性，不测声学质量或端到端延迟，也不覆盖所有弱网、手机厂商后台策略、雷达重新接入、备用电池切换或量产电源工况。此前断开的根因尚未确定；不能仅凭本轮通过就归因于电源，或宣称此前所有故障均已排除。

## 复现与原始记录

串口桥及 ADB 准备步骤见[Android 测试说明](android/README.md)。关键参数：

```powershell
$env:VOICE_TEST_HOLD_SECONDS='1800'
$env:VOICE_TEST_SKIP_ICE_REFRESH='1'
$env:VOICE_TEST_SAFE_DIAGNOSTICS='0'
$env:VOICE_TEST_OUTPUT='build/real-call-30min-next'
F:/nodejs/nvm/v22.16.0/node.exe tests/android/real-esp32-network-recovery.mjs --real-device 189833342344184
```

本机结果、摘要和条件记录：`build/real-call-phone-charger-current-30min/results.json`、`summary.json`、`test-context.json`；串口原始记录为 `build/esp32-real-call-live.log`。这些文件留在 Git 忽略的目录，不上传原始连接数据。源码/镜像指纹为 `build/current-diagnostic-source-manifest.json`。

测试结束已恢复雷达采集服务、18890 电源观察页面及 18891 TTL 的 live 来源；采集目录为 `build/radar-monitor-20261120-193710`。仅关闭本轮隔离 ADB 5038，保留用户 ADB 5037 和模拟器。
