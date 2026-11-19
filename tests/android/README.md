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
