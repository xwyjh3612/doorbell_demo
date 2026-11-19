# 语音对讲 Android App

独立应用 `com.youkong.voiceintercom`，只对接本项目 ESP32 语音协议。现有 video call 项目仅提供原生 WebRTC 实现参考；不共用其账号、接口、服务器或应用标识。

演示安装与操作见 [安卓演示说明.md](../安卓演示说明.md)。

0.3版使用深色设备演示台，通过独立只读WSS `/telemetry?device=设备ID`接收可选雷达快照，展示存在/活动、呼吸、心率、距离和近两分钟实际数值趋势；静音/扬声器控制在呼叫中显示，技术日志默认折叠。观测通道不会注册接听ID或影响通话状态机。数值按设备采集年龄、服务器缓存年龄和Android单调时间判定过期，不合成波形、不将零值当成有效测量。

需要 JDK 17、Android SDK 35、Gradle 8.9 或以上。默认生成测试签名 APK，适合演示安装。

```powershell
./tools/build-android.ps1 -JavaHome F:/android/Java/jdk-17.0.11 -SdkHome F:/android/sdk -GradleHome F:/android/gradle/8.10.2
```

App 通过 HTTPS/WSS 请求服务器下发 ICE 配置，使用原生音频 WebRTC。`offer/answer` 的 SDP 放在 `data`，ICE 下行使用字符串 `candidate`；支持振铃后 `ACCEPT_CALL` 握手和直接 offer 来电。远端候选暂存到远端 SDP 设置成功后再提交。App 只使用 TURN relay，首个 SDP 包含已经取得的中继地址，再发送后续新增候选，避免旧版 ESP32 peer 在内网候选或不完整协商状态下提前失败。该等待只发生在接通前，不增加媒体缓冲。所有状态和异步回调通过主线程串行处理，结束时使旧连接回调失效。

演示版仅支持页面打开时来电。没有后台服务、推送或锁屏来电通知，切到其他应用会挂断并关闭信令；正式后台来电需要后续单独实现。App 不声明摄像头、定位或悬浮窗权限。
