# 原生 App 外网通话验证

`native-app-e2e.mjs` 使用安卓模拟器里的原生 App，浏览器模拟一个 ESP32 信令端，通过真实服务器的 WSS ↔ MQTT 桥接建立 WebRTC 音频；浏览器强制 TURN relay。没有使用 video call 接口，也不往真实 ESP32 ID 发信令。

需要 Node.js 22、已安装 Playwright 的目录、Edge/Chrome、已启动的安卓模拟器和已安装的 debug APK。模拟器须授权麦克风并能解析外网域名。脚本会把模拟器 App 的配置改为隔离的测试 ID：`demo_virtual_20261119` / `demo_app_20261119`；测试后需在设置页恢复实际设备 ID，或恢复原偏好文件。

```powershell
$env:VOICE_TEST_ADB='F:/android/sdk/platform-tools/adb.exe'
$env:VOICE_TEST_SERIAL='emulator-5556'
$env:VOICE_TEST_PLAYWRIGHT='C:/project/esp32/doorbell_demo_voice/build/radar-browser-tools'
$env:VOICE_TEST_BROWSER='C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'
F:/nodejs/nvm/v22.16.0/node.exe tests/android/native-app-e2e.mjs
```

输出位于忽略的 `build/android-e2e/`，包含结果和界面截图。测试断言 native UI 到达通话状态、模拟端收到/发出音频 RTP 包、TURN relay 使用、`ACCEPT_CALL`/`bye`/`reject` 确实通过 MQTT 到达模拟设备。静音和扬声器测试检查按钮状态，不代表已验证实体手机的声学表现。

0.4 增加后台、Activity 结束、PIN 锁屏、强制 Doze、息屏音频及通知拒接测试，设置 `VOICE_TEST_BACKGROUND=1` 启用。Android 14 以上设置 `VOICE_TEST_FALLBACK=1` 可验证全屏权限拒绝后的通知接听。必须使用模拟器并预先解锁、允许麦克风和通知；测试会临时设置 PIN、电池豁免和 Doze，结束后恢复偏好、清理测试锁和停止 App。

`VOICE_TEST_DEVICE` / `VOICE_TEST_LOCAL` 支持独立 `demo_` ID，`VOICE_TEST_OUTPUT` 指定输出目录，`VOICE_TEST_BACKGROUND_ONLY=1` 只运行后台场景。并行运行须使用不同设备、接听和 MQTT client ID；MqttProbe 已为每个设备及进程生成独立 client ID。专项记录见 [安卓后台与锁屏接听验证.md](../../安卓后台与锁屏接听验证.md)。

`real-esp32-call-e2e.mjs` 用于真实设备测试，必须显式指定 `--real-device 189833342344184 --hold-seconds 60`。App 设置为相同的真实设备 ID；先停止占用 COM13 的雷达采集，在项目根目录的一个终端启动本地串口桥接：

```powershell
F:/Espressif/python_env/idf5.4_py3.11_env/Scripts/python.exe tests/android/esp32-call-console.py --port COM13
```

桥接在 `http://127.0.0.1:18889` 提供状态行及白名单命令 `cmd ring/answer/reject/close`，并独占 ESP32 控制台。另一个终端沿用上方 ADB 环境变量，运行：

```powershell
F:/nodejs/nvm/v22.16.0/node.exe tests/android/real-esp32-call-e2e.mjs --real-device 189833342344184 --hold-seconds 60
```

可通过 `VOICE_TEST_CONSOLE` 覆盖本机桥接地址。测试后以 Ctrl+C 关闭桥接，再执行 `./examples/radar_monitor/start.ps1` 恢复采集。桥接的原始串口日志仅保存在被忽略的 `build/`。

真实流程测试读取板子的 `esp_webrtc_query` 音频统计，同时核对 App“通话中”状态，覆盖双向呼叫、双方挂断、双方拒接和再次呼叫。输出仅保存音频包统计和结果，不保存完整的原始 MQTT/SDP 日志，避免把中继凭据写入公开测试记录。

`radar-voice-e2e.mjs`验证0.3版App与真实60G语音固件的联合行为。模拟器接听ID须设为独立`lead_demo_test_20261119`，目标为真实ESP32；使用同一本地串口桥接，通过App主动呼叫设备，检查来电铃声触发、35秒及再次15秒双向音频、通话期间雷达继续接收/暂停上传、挂断后恢复上传、静音及设备拒接。

```powershell
F:/nodejs/nvm/v22.16.0/node.exe tests/android/radar-voice-e2e.mjs --real-device 189833342344184
```

输出为忽略的`build/radar-voice-e2e`。测试完成后停止模拟器App并恢复偏好，避免后续与真实手机争用ID。此联合脚本仅通过App呼叫真实设备；设备呼叫App另外由隔离模拟设备验证，不把该结果描述为双向真实板子全流程。
