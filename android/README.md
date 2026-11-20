# 语音对讲 Android App

独立应用 `com.youkong.voiceintercom`，只对接本项目 ESP32 语音协议。现有 video call 项目仅提供原生 WebRTC 实现参考；不共用其账号、接口、服务器或应用标识。

演示安装与操作见 [安卓演示说明.md](../安卓演示说明.md)。

当前0.5版把中央圆形改为基于真实上报状态的人体轮廓与动效，并通过HTTPS `/api/devices/{device}/radar-history`显示服务器保存的时间线。可查看最近一小时、今天或过去30天的日期；无上报时明确显示无数据。历史读取属于页面观察通道，页面离开后取消请求。可恢复音频中断的8秒自动挂断已移除，详见[音频恢复验证](../安卓音频恢复验证.md)。

0.3版使用深色设备演示台，通过独立只读WSS `/telemetry?device=设备ID`接收可选雷达快照，展示存在/活动、呼吸、心率、距离和近两分钟实际数值趋势；静音/扬声器控制在呼叫中显示，技术日志默认折叠。观测通道不会注册接听ID或影响通话状态机。数值按设备采集年龄、服务器缓存年龄和Android单调时间判定过期，不合成波形、不将零值当成有效测量。

需要 JDK 17、Android SDK 35、Gradle 8.9 或以上。默认生成测试签名 APK，适合演示安装。

```powershell
./tools/build-android.ps1 -JavaHome F:/android/Java/jdk-17.0.11 -SdkHome F:/android/sdk -GradleHome F:/android/gradle/8.10.2
```

App 通过 HTTPS/WSS 请求服务器下发 ICE 配置，使用原生音频 WebRTC。`offer/answer` 的 SDP 放在 `data`，ICE 下行使用字符串 `candidate`；支持振铃后 `ACCEPT_CALL` 握手和直接 offer 来电。远端候选暂存到远端 SDP 设置成功后再提交。App 只使用 TURN relay，首个 SDP 包含已经取得的中继地址，再发送后续新增候选，避免旧版 ESP32 peer 在内网候选或不完整协商状态下提前失败。该等待只发生在接通前，不增加媒体缓冲。所有状态和异步回调通过主线程串行处理，结束时使旧连接回调失效。

0.4版参考 `C:/project/java/video-call` 的前台服务、独立 `IncomingCallActivity`、通知 PendingIntent 和权限降级实现后台及锁屏接听。协议、账号和 WebRTC SDP 格式仍独立于 video-call。

- `CallService` 持有 WSS、待接 offer、早到 ICE、超时和音频连接。退出页面、返回桌面或 Activity 销毁不会挂断；只在明确挂断、拒接、网络失败或超时结束通话。
- 待机使用 `specialUse` 前台服务，常驻通知可关闭后台接听。用户点击呼出或接听、Activity 可见时才启用 `microphone` 服务类型；先振铃后 offer 的流程也在发送 `ACCEPT_CALL` 前完成提升，避免 SDP 后到时触发 Android 14 的后台麦克风限制。
- 高优先级来电通知可接听/拒接。锁屏全屏入口使用独立、非导出的 Activity；接通后进入原演示台，音频一直归服务持有。PIN 锁不解除，也能在锁屏上接听。
- Android 15 的具体通知 Activity PendingIntent 显式允许背景启动。全屏权限未获准时使用普通接听/拒接通知；CallStyle 被系统拒绝时尝试普通通知，不中断信令服务。
- 通知操作携带每次来电的独立 token，旧通知无法接听或挂断下一通来电。远端挂断/超时清理通知、铃声、震动和来电页面。
- 后台心跳、网络变化重连及带超时续期的 CPU wake lock 保持待机连接；Doze 下的网络需用户解除电池优化。常驻待机有耗电，用户可从通知关闭。

首次安装请允许麦克风及通知，并在 App“后台与锁屏来电设置”中允许全屏来电、解除电池限制。部分厂商另需允许自启动和后台运行。系统强行停止、用户停止前台服务或重启手机后需要重新打开 App；当前没有厂商推送、FCM或开机自启动。App 不声明摄像头、定位或悬浮窗权限。

平台依据：
- https://developer.android.com/develop/background-work/services/fgs/service-types
- https://developer.android.com/develop/background-work/services/fgs/restrictions-bg-start
- https://developer.android.com/develop/ui/views/notifications/call-style
- https://developer.android.com/training/monitoring-device-state/doze-standby
