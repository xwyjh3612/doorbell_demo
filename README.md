# ESP32 4G 语音对讲

本项目是基于 ESP32-S3 + ML307 4G 的双向实时语音对讲系统。ESP32 使用 MQTT，安卓 App 和浏览器使用 WebSocket/WSS，`audio_server` Spring Boot 服务在两者之间转发 WebRTC 信令。双方通过 WebRTC/UDP/TURN 进行 Opus 16kHz 单声道语音对讲，信令服务不承载音频编解码。

独立安卓 App 支持呼叫、接听、拒接、挂断和麦克风控制，在线下载与现场操作见 [安卓演示说明.md](安卓演示说明.md)。演示入口：[https://voice.2811.top/demo.html](https://voice.2811.top/demo.html)。

当前先按 [首批5台分阶段实施方案](首批5台分阶段实施方案.md)推进：保留完整开发板和现有模块，5台先做直供电装盒演示，基础物料预算约565元；并行以 [1套成品UPS手工接线验证](手工接线备用电源验证方案.md)提前检查断电接管，UPS另询价。演示通过后做3～5台计划生产架构的PCB样机，再做10台生产试装和100台小批生产。

2026-11-20当前先选 [UPS HAT(D)现售套装测试电源](当前备用测试电源方案.md)：板框56×85mm、厂家两节21700并联，公开基价138元；全部新购测试电源参考172元，税运另计。手工焊输出引线，先放机外测2A/断电/复电，管理信号随后接；本机未实测。[Mini小电池评估](UPS_Module_Mini测试电源方案.md)保留候选，但默认充电电流与小电池匹配、信号电平未确认，暂不作为直接充电测试首选。

完整产品需求、结构/PCB协同设计、软件运维和生产交付见 [从样机到小批销售和量产的完整路线](语音对讲产品从样机到量产路线.md)。开发板演示不能替代后续新PCB和批次工艺验证。

设备呼入使用双短电话铃，呼出使用回铃音；MQTT 联网后播放中文“联网成功”。音频素材与重新生成方法见 [提示音说明](main/call-tones.md)。

长期外接电源、偶尔断电由小电池接管的电源模块选型与接线见 [长期插电与备用电源](长期插电与备用电源.md)，包含 5V I2S 功放负载。

准备定制主板时，参阅 [首版PCB与备用电源选型](首版PCB与备用电源选型.md)：按5V/2A目标，推荐TP4056＋TPS61230A＋TPS2117电源组合，列出料号、参考电路、采购依据及原理图/PCB打样步骤。

此前已画出 [可编辑原理图与PCB元件摆放草图](hardware/voice_carrier_v1/README.md)，保留可选生命体征雷达接口；PCB尚未布线，外壳及模块实物尺寸待核对。[带定制底板和备用电池的5台与100台预算](首版5台与100台成本.md)分别约1000元、1.39万元，属于后续候选配置，尚未取得完整供应商报价，不是当前直供电5台的采购预算。

后续评估定制备用电源底板时可参考 [此前采购与贴片清单、电路图和询价说明](outputs/first5-supplier/首批5台采购与商家询价.md)：底板每块42个SMT元件、13个插件，现有模块另外组装。当前5台直供电阶段不用这份底板BOM下单，后续设计与验证完成后再发布生产文件。

以现有约60元语音硬件为基准，备用小电池、电源管理、外壳和定制主板的增量预算，以及可选生命体征检测清单，参阅 [硬件清单与成本预算.md](硬件清单与成本预算.md)。

先用现有开发板制作带外壳和面板按钮的演示样机，选型、采购搜索入口及GPIO接线参阅 [演示样机外壳与按钮.md](演示样机外壳与按钮.md)。

## 协议约束

**ESP32 现有协议和官方 WebRTC/peer 组件保持不变。兼容转换在 Java 服务端完成。**

| 消息 | ESP32 上行字段 | ESP32 下行字段 | 浏览器常用字段 |
| --- | --- | --- | --- |
| `offer` / `answer` | `data` | `data` | `sdp` |
| `candidate` | `data` | `candidate` | `candidate` |
| `version_report` | `version` 为字符串 | — | 服务端转为整数 |
| `ota` | — | `url`、数字 `version`、可选 `md5` | 服务端配置 |

Java `SignalingMessage.normalizeMediaFields()` 补齐两种媒体字段，不改变设备使用的字段。因此默认 `index.html` 和 `index2.html` 均可使用。

## 当前通话行为

- 本地挂断只关闭媒体连接，保留 MQTT 信令实例，允许下一次呼叫。
- 只有主叫且已经成功接通过一次，异常断开后才自动重拨。等待 1500ms，最多重试三次；重拨连接失败或超时会继续剩余尝试。
- 等待重拨时状态为 `RECONNECTING`，可以主动挂断取消。对端明确 `bye` / `reject` / `timeout` 结束通话，不触发重拨。
- 呼出及接听后的连接超时使用 NVS 配置 `call_timeout`，默认 120 秒；0 或超过 3600 秒的旧配置回退为 120 秒。收到 answer 后仍等待实际 WebRTC connected，避免卡在连接中。
- 固定 `call_control` 任务串行处理命令、框架事件和截止时间。框架回调只入队，不在 peer 自身线程中等待关闭 peer。
- 固定 `mqtt_messages` 任务按接收顺序处理下行消息，避免每条消息创建临时任务。队列容量分别为 24 和 16；队列满时记录错误。
- 设备接听过来电后再次呼出，先更新缓存 ICE 的主叫角色，再启动媒体连接，避免交替呼叫时沿用上一通的被叫角色。

## OTA

仅在空闲状态启动升级，升级期间禁止新呼叫。URL 与 MD5 在创建下载任务前检查。MD5 缺失或为空时保持现有升级行为；提供 32 位十六进制 MD5 时，在接收数据期间计算，下载完成后比对。校验失败不会切换启动分区，并释放 OTA 写入句柄。

## 构建与测试

雷达检测为编译时可选，默认关闭。运行`./tools/build-firmware.ps1 -Variant voice`生成基础语音版，`-Variant voice-radar`生成24G感应版，`-Variant voice-radar60`生成60GHz呼吸/心率版；关闭时不编译雷达模块和入口。App 0.3支持感知数据及实际数值趋势，通话期间暂停网络上传、继续本地雷达接收。接线、配置开关和验证说明见[可选雷达固件.md](可选雷达固件.md)。

恢复以前的整套联调环境，参阅 [测试环境恢复.md](测试环境恢复.md)。在项目根目录运行 `./audio_server/start-test.ps1` 可启动本机 Java 服务。

R24D 人体感应雷达的独立读取 demo 见 [examples/radar_uart_demo/README.md](examples/radar_uart_demo/README.md)，实测记录见 [TEST_RESULTS.md](examples/radar_uart_demo/TEST_RESULTS.md)。使用 UART2、TX=GPIO8、RX=GPIO5，不改动主程序的通话协议。

换到开发板丝印TX/RX后的独立诊断程序见 [examples/radar_pin_demo/README.md](examples/radar_pin_demo/README.md)。当前`rx44-1`版使用原生USB控制台，UART2默认GPIO44/115200只接收，运行时可切换GPIO43/44/5与波特率；接GPIO44需隔离板载CH343发送端，GPIO43替代测试需在程序启动并切换配置后才接入。

雷达改回GPIO5/8并使用CH343 UART口（本机COM13）的独立测试版见 [examples/radar_gpio5_demo/README.md](examples/radar_gpio5_demo/README.md)。当前`rx5-uart-2`默认GPIO5/115200接收，支持GPIO6/8切换，保存最近512字节；GPIO8不作为发送输出，重启恢复GPIO5。两个demo的控制台接口不同，采集脚本会检查设备及运行程序。

GPIO6持续采集与实时监测页面见 [examples/radar_monitor/README.md](examples/radar_monitor/README.md)，本机地址为 [http://127.0.0.1:18888](http://127.0.0.1:18888)。已验证GPIO6/115200的有效初始化及多次有人/无人上报，页面区分历史数据、新报文及设备串口连接状态。

新接入的 R60ABD1 60GHz 呼吸睡眠雷达演示见 [examples/radar_r60abd1_demo/README.md](examples/radar_r60abd1_demo/README.md)，本机页面为 [http://127.0.0.1:18890](http://127.0.0.1:18890)。沿用 GPIO6 接收，电脑端解析呼吸、心率、体动和距离，无需替换语音固件。

固件使用 ESP-IDF 5.4.3，当前目标为 ESP32-S3、8MB Flash、PSRAM。进入已激活的 ESP-IDF 环境后运行：

```sh
idf.py build
```

服务端需要 Java 8 和 Maven：

```sh
cd audio_server
mvn test package
```

主机测试编译完整的应用源文件，仅替换平台 include 和硬件 API。OTA 测试使用 ESP-IDF 中真实的 Mbed TLS MD5 实现，模拟下载分片与分区写入：

```sh
python -m pip install --target build/host-tools ziglang
python tests/run_host_tests.py --idf /path/to/esp-idf
```

也可通过 `--compiler` 指定 clang、gcc 或 zig。脚本可从现有 `build/project_description.json` 自动读取 ESP-IDF 路径。

当前自动化覆盖 9 个通话场景（含呼入、呼出和联网提示音）、8 个 OTA 场景、4 个 UDP 最新包场景、雷达解析及上传保护、14 个 Java 协议/观测/路由用例，以及9个Android状态检查。UDP 测试使用实际双线程，验证主动丢旧包、读取快照完整性及 10 万次并发覆盖；改动和验证边界见 [tests/udp_receive_notes.md](tests/udp_receive_notes.md)。主机测试不验证 ML307 实际网络、音质或设备重启，需要硬件联调确认这些行为。

## 阅读入口

- `main/main.cpp`：设备初始化。
- `main/webrtc_mqtt.c`：通话控制与重拨。
- `main/mqtt_signaling.cpp`：保持现有设备协议的 MQTT 实现。
- `main/otaupgrade.cpp`：HTTP OTA、校验与资源清理。
- `audio_server/src/main/java`：WebSocket 与 MQTT 信令桥接。
- `MAIN系统功能梳理.md`、`MQTT信令简要说明.md`、`audio_server/AI_PROJECT_GUIDE.md`：详细模块说明。
