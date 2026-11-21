# ML307R与实时语音传输路线审查

本次仅分析代码、实机日志及官方文档，没有修改固件、切换模组USB模式或中断测试。结论：优先验证现有ML307R的USB RNDIS路线；不能认定换模组即可解决掉话。

## 已确认的现有路径

`components/esp-ml307/src/ml307/ml307_udp.cc`对不超过730字节的数据转HEX后用AT+MIPSEND发送，等待命令应答及发送完成。超过730字节使用固定长度数据输入。`components/esp-ml307/src/at_uart.cc`的SendCommandWithData持有command_mutex_，MQTT控制和UDP发送共用这个命令入口。

UART为921600、8N1时单向理论字节带宽约92,160B/s；HEX编码使媒体载荷占用两倍字符，再加命令与应答。这是接口理论预算，不能据此确定当前语音实际带宽已满。更直接的风险是发送应答或共享命令锁等待占用实时线程；主动丢旧接收包不会消除已经发生的同步发送阻塞。

已有实机轮次记录到UDP AT应答超时后AFE FEED满；一些失败随后有MATREADY，另一些捕获时没有。时间先后支持继续排查发送等待与fetch受阻，不证明所有失败来自AT方案，也不排除供电、接触、模组固件或驱动状态异常。USB路线仍须保留低延迟策略、队列上限、媒体过期丢弃和重连处理。

用户用万用表测到约5.22–5.26V，测量点未确认。40mV约为0.8%，不能单凭末位跳动判断仪表故障或供电异常，也不能用平均读数排除瞬态压降。实机日志中的MATREADY没有被解释为已证明的电源故障。

## 优先选择：同模组USB RNDIS

乐鑫官方[`iot_usbh_rndis`文档](https://github.com/espressif/esp-iot-solution/blob/master/docs/en/usb/usb_host/usb_rndis.rst)明确列出ML307R，测试固件ML307R-DC-MBRH0S00，ESP32-S2/S3/P4均支持。提供[官方USB RNDIS示例](https://github.com/espressif/esp-iot-solution/tree/master/examples/usb/host/usb_rndis_4g_module)及[驱动组件](https://github.com/espressif/esp-iot-solution/tree/master/components/usb/iot_usbh_rndis)。该记录并非对当前ML307R-DL实物、固件或长通话的验收。

RNDIS让模组作为USB网卡，对ESP32提供网络接口。WebRTC UDP、MQTT都可以走ESP网络栈，避免每个语音包用MIPSEND收发。AT仍用于必要的初始化和状态控制；不会宣称新架构完全不使用AT，也不会保证没有网络缓冲和延迟。

当前ESP32-S3 USB D-/D+为GPIO19/20，实际CUSTOM_AUDIO_BOARD使用麦克风14/13/12、功放15/16/7，当前实际音频引脚没有占用19/20。必须核对实物开发板USB端口、Host VBUS/USB_DETECT供电、GND、ESD和模组USB描述符。模块VBAT不能接5V；本体供电与USB检测电压须分别处理。

本地已设计的V2仅把模组USB引到维修口，并未连接ESP32 USB Host；若正式采用RNDIS，主板必须补GPIO19/20接口与90Ω差分走线设计，不能把现有未布线草图当作已经兼容。四针TTL刷机口有助于保留独立刷机路径，但开发板USB/电源冲突仍需核对。

当前工程使用定制UDP适配层及模组MQTT接口。迁移并非只换两根线：需要对接普通socket/网络接口、保留现有信令消息/主题、重连状态、设备身份与服务器行为；媒体实现和官方协议保持。ESP端依然使用MQTT，App依然使用WSS；传输栈实现可以变化。

不在当前通话中发送USB模式切换、+++、ESC或reset。另建可回退测试工程，先验证RNDIS入网/DHCP/UDP/DNS，再接现有语音协议，比较相同SIM、供电、天线、服务端和测试条件。验证来回呼叫、独立半小时及更长通话、反复拨打、断网恢复、插拔、低电切换、发送延迟与错误统计。

## 备选：USB PPP与其他模块

乐鑫[`iot_usbh_modem`官方USB PPP支持表](https://github.com/espressif/esp-iot-solution/blob/master/docs/en/usb/usb_host/usb_ppp.rst)列出Air780E、EC600N-CN、EC20、A7670E、LE270-CN等及具体测试固件。相同型号可能有不同固件，必须核对USB PPP能力、AT/数据接口、频段和可采购版本。

对成本敏感纯语音项目，Cat.1通常是优先询价范围；不要因为Cat.4峰值更高就假设通话更稳定。Air780E AT固件版、EC600N-CN可作为对照候选，尚未询到实际量产报价，未冻结为采购BOM。SIM7080G等低速/特定蜂窝制式产品即使出现在通用PPP表，也不能当作当前4G实时语音的等价替代。

UART PPP可以避免逐包AT命令，但串口带宽、驱动任务与缓存仍需评估。USB PPP使用拨号后的数据接口传IP包；优先选择能独立AT控制的版本，避免通话中退出数据模式查状态。ECM/RNDIS与PPP是不同USB网络路线，必须选匹配驱动，不能混称。

早期建议比较USB PPP新模组，随后查到官方明确支持ML307R的RNDIS，最终优先级据此更新为同模组RNDIS对照；不是已完成迁移或验收。

## 官方WebRTC仓库的范围

[esp-webrtc-solution](https://github.com/espressif/esp-webrtc-solution)提供WebRTC媒体组件和应用示例。[esp_modem](https://github.com/espressif/esp-protocols/tree/master/components/esp_modem)及IoT Solution提供蜂窝联网基础。两者需要工程集成，并不构成一套已经为当前硬件、运营商和Android App验收的完整4G对讲产品。

本次参考文件下载至本地Git忽略的build/cellular-architecture-review，不含业务MQTT凭据或SDP。官方USB吞吐量示例不能直接当作本项目的延迟/稳定性指标；更优方案最终依据实机对照、供应链和整机成本。

## 商家资料核对与用户授权测试

用户随后提供本机商家资料文件夹。19份PDF共902页已本地提取，用于核对型号和命令；原PDF与全文不复制进Git。记录如下：

- 《ML307R_拨号上网用户手册_V1.0.1》p7明确适用于ML307R-DL；p9/p16给出RNDIS配置，p20给出ECM配置；USB模式变更重启后生效且掉电保存。p10/p17使用AT+MDIALUP=1,1拨号，p11列VID 0x2ecc/PID 0x3012、USB AT接口2，PPP拨号接口为“-”。不能把本模组RNDIS/ECM路线与别的模组PPP方案混为一谈。
- 《ML307R_硬件设计手册_AT版本适用_V1.1.1》p22/p27：USB_DP59、USB_DM60、USB_VBUS61；VBUS检测范围3–5.25V，不是模块主电源。p24再次要求VBAT 3.4–4.5V、2A瞬态、两颗220µF，以及重新上电前1.8V以下至少100ms。
- 《扩展AT用户手册_4G系列_V1.7.2》p45–47的通用MDIALUPCFG参数有型号例外：ML307R不支持通用workmode参数、指定auto的cid、NCM模式、完整MDIALUPCFG?等。不照搬其他模组命令。p50–51注明ML307R不支持MCHIPINFO，不能依靠这条指令代替电源实测。
- 《ML307R_维护诊断工具用户手册_V1.1.0》p14–18为CATStudio USB日志抓取，要求匹配固件DBG；p19–20提供MDUMPCFG=1及YmodemDump。启用Dump会改变故障后的状态，须另做诊断阶段，不能混进原基线测试并声称条件相同。
- 既有日志只读核对实物固件为ML307R-DL-MBRH0S01；不同于乐鑫RNDIS表的DC/MBRH0S00测试版本，仍需实物USB枚举、拨号及通话验证。

用户明确授权按照优先级尝试各方案。执行顺序：完成当前AT基线追加五轮；用独立工程测试ML307R USB RNDIS及AT控制并存；通过基础网络后接现有通话协议，实测呼入/呼出/BOOT接听/挂断/再次拨打与长通话；然后对照ECM；只有必要时才选择其他模块PPP。长期透传不作为优先路线，用户已反馈过去同串口透传中无法执行挂断。

当前USB网络独立探针只准备基础联网与控制查询，不能计为实际通话验收。电脑当前仅识别到ESP CH343 COM13，未识别ML307 USB；ESP USB Host线缆是否连接仍待确认。现有语音固件运行期间不刷写网络探针、不切USB模式、不发模组reset。
