# ML307R-DL USB RNDIS / ECM 独立联网测试

这是独立的基础网络探针，用于验证现有ML307R-DL能否作为ESP32-S3 USB网卡。**没有语音、MQTT或WebRTC，不能据此宣布通话稳定。** 不在当前半小时语音测试期间刷写。

优先RNDIS，随后ECM。普通AT控制保留在GPIO17/18、DTR4，与USB媒体数据接口分开；没有进入UART透传。基于乐鑫官方`iot_usbh_rndis`0.5.3、`iot_usbh_ecm`0.4.0、`iot_usbh_cdc`3.1.1、`iot_eth`1.1.0。官方源码固定commit `f721a40c032f6168844fe3bd321bc182e2593348`，克隆到项目build/esp-iot-solution-cellular；不修改原厂驱动。

## 接线前提

| ML307模块端 | ESP32-S3端 |
| --- | --- |
| USB D+ | GPIO20 / 原生USB D+ |
| USB D- | GPIO19 / 原生USB D- |
| GND | GND，共地 |
| USB VBUS检测 | 稳定、符合模块手册范围的5V |
| 模块主电源 | 保持现有合规供电；裸模组VBAT不能接5V |

不要把USB D+/D-接到TTL TX/RX。原生USB接口连接Host后，保留独立CH343/TTL刷机通路。开发板USB端口是否是Host可用接口、VBUS是否倒灌必须按实物核对。手搓长杜邦线不作为USB可靠性验收接线；优先短USB线和正确Host转接。雷达及功放接线保持当前已测配置。

已从商家手册确认DL支持RNDIS/ECM，实物日志版本为ML307R-DL-MBRH0S01。先枚举VID/PID及接口，匹配预期0x2ecc/0x3012。官方支持表测试的是DC子型号/MBRH0S00，仍需要当前实物验证。

## 构建与行为

启用ESP-IDF5.4.3环境后，从仓库根目录运行`build.ps1`。RNDIS/ECM使用各自独立build目录和sdkconfig，不会覆盖根项目固件构建。默认RNDIS，MODE变更权限关闭：启动时仅查询模式，若与目标不同就停止，保留配置。

开启`-AllowModeChange`测试配置后，仅在模式不同的情况下执行一次对应模式配置与软重启；这是持久配置，后续切回AT基线需要记录当前配置和恢复步骤。测试阶段不得重复重启掩盖故障。使用独立APN参数时先记录原PDP配置，默认空值不修改。

联网通过UART执行AT+MDIALUP=1,1；USB数据通过esp_netif，查询日志仅显示模式、已获IP次数、连接/断开次数、DNS/TCP443结果和内存。每5分钟检查voice.2811.top DNS与TCP443连接，无大文件下载，无Wi-Fi AP或网页配置，不打印完整AT、媒体或凭据。

不擦除NVS，不提供自动全片擦除/全量刷写命令。任何探针刷写前，先保存当前app镜像、分区表、OTA选择和NVS；按实物分区选择测试槽并验证回退。已有voice-radar60.bin只是一份app镜像，不能单凭该文件盲刷分区或OTA状态。

## 验收顺序

1. USB设备枚举、驱动连接、拨号、DHCP/DNS/UDP基础联通。
2. AT控制查询与USB网络并行；主动关闭网络、重新连接必须另记操作时点，不混入自然掉线结果。
3. 集成同一套语音信令与媒体协议，保留UDP丢旧包及发送时限；ESP端MQTT、App端WSS。
4. 呼入、BOOT接听、挂断、再呼叫、呼出、App后台/锁屏，分别验收。
5. 相同SIM/供电/天线/服务器做多轮独立30分钟及长通话，对照AT/RNDIS/ECM；保留所有失败及未接通尝试。

基础探针与语音候选使用独立构建目录。V2 PCB已增加ESP USB Host选装接口及两组互斥0Ω电阻，见[板图说明](../../hardware/voice_mainboard_v2/README.md)。差分布线、ESD与实际Host连接尚未完成，现有维修USB口不等于已验证USB网络。

## 已识别当前小板的物理限制

用户照片为LeLian Tiny CORE V1.1 ML307R-DL小板，六针标BAT/EN/RX/TX/GND/VIN，未见USB插座或标注的D+/D-。照片背面底部若有未标注测试焊点，仍须小板原理图或商家连通性确认，不能按外观指定它们为USB。BAT与EN不代替数据脚，也不能把5V直接接裸模组VBAT。

厂家提供的裸模组手册和标准EVB手册没有证明这个Tiny CORE把59/60/61脚引出。可用路线：取得这块小板的USB焊点/原理图，或用同型号带USB数据口的开发板做对照。暂时不指导从细密裸模组焊盘直接飞线，手工USB布线不作为量产可靠性依据。

## 隔离语音候选版本

`prepare_voice_test.py`从包含AT恢复修复的固定commit `b932fba5a14013653ef8f2e9756969b756e59a54`在Git忽略的`build/voice-usb-evaluation-recovery`生成拷贝；`build_voice_test.ps1`分别编译RNDIS/ECM。实验只将原UdpManager的UDP对象替换为USB原生socket传输，保留LatestUdpPacket、MQTT AT控制、官方媒体和信令协议；不修改根项目源码。旧17a62a4候选保留在`build/voice-usb-evaluation`，不会覆盖。

USB媒体发送使用非阻塞socket，失败丢弃，不积压重试。接收线程有20ms超时，退出确认后才关闭fd；接收回调仍覆盖旧包。实际网络队列、调度、声学延迟需要实测，不能把socket非阻塞等同于端到端零延迟。

本次发现原基线在网络恢复时有MQTT对象与雷达线程并发使用的生命周期问题，已留存匹配ELF调用栈。根项目的AT恢复版本已修复对象复用、连接状态读取及URC回调工作线程调度，并正在做实机回归；当前隔离USB语音候选同步这些修复。USB断网/枚举恢复与应用状态联动仍须实测，不能把AT恢复通过等同于USB恢复通过。当前小板USB未引出，USB候选未刷写、未通话验收。

2026-11-21恢复基线的RNDIS/ECM均通过ESP-IDF5.4.3编译。RNDIS app 2,899,136字节、SHA256 `122972d7b1aaa01ada5d2014b9ddf887711a5173b809ade0283d4224a43ad2d7`；ECM app 2,892,544字节、SHA256 `5b6e48530d13a1a92ba55cfaa67d46654b663164cde1931c2eb9c91e599702ad`。构建清单位于隔离目录各`build-*/test-manifest.json`，标明未刷写/未实机通话。编译结果不加入当前AT的40轮统计。

参考：[官方RNDIS驱动](https://github.com/espressif/esp-iot-solution/tree/master/components/usb/iot_usbh_rndis)、[官方RNDIS示例](https://github.com/espressif/esp-iot-solution/tree/master/examples/usb/host/usb_rndis_4g_module)、[路线评估](../../tests/cellular_transport_review_20261121.md)。商家PDF保留在用户原文件夹，不上传。
