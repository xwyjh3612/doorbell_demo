# ML307C USB诊断可行性识别

这是语音对讲项目的独立ESP32-S3调试固件。它通过官方ESP-IDF USB Host枚举设备，读取接口名称，并对已确认的Mobile Diag Interface执行一次最多64字节、45秒的只读接收。另通过实际匹配的Mobile AT Interface依次查询AT响应、固件版本和Dump配置；可在明确启用构建选项后发送手册规定的`AT+MDUMPCFG=1`并读回验证。没有实现CATStudio实时日志启用和解码协议，也不传输通话音频。识别或打开接口不能替代完整崩溃诊断。

本固件不链接语音对讲代码，不修改官方WebRTC协议或主动丢旧包策略。临时安装它期间不能通话，因此这些尝试不属于正式40轮。2026-11-25用户接好USB数据线后，已临时安装此demo；原921600语音加60G雷达镜像及完整设备备份保存在根目录build，供诊断后恢复。

## 接线

Tiny V3.02的正面朝向为金属屏蔽罩朝向观察者、天线座在上方。

| Tiny小板 | ESP32-S3 |
| --- | --- |
| 右列第3脚N，USB D− | GPIO19，USB D− |
| 右列第4脚P，USB D+ | GPIO20，USB D+ |
| GND | ESP32 GND，共地 |
| VCC | 保留原稳定5V板级供电 |

上表是Tiny手册给出的标注。现场首测为低速且枚举失败，用户重新接线后控制器已识别全速设备；请保留当前实测成功的接线方向。S3侧D−固定GPIO19、D+固定GPIO20，但小板P/N的现场对应还未通过照片或通断测量确认，不能单据软件结果断定丝印错误。

USB数据线尽量短并成对走线。3V8入口不能接5V。不要把两路独立5V电源直接并联；也不要使用ESP32的3.3V引脚给4G板供电。USB连接不会使GPIO19/20输出5V。

ESP32的GPIO19/20对应原生USB，不能同时用原生USB接口连接电脑。电脑日志仍通过既有CH343 COM13的UART控制台读取。当前语音音频真实配置使用GPIO12～16及GPIO7，与19/20无重叠；旧I2S_CHECK提示文字中的20/19/21不是实际CODEC_INIT配置。现用固件仍启用USB Serial/JTAG副控制台，安装这个demo前不能直接认为接线即可运行。demo使用UART控制台并关闭USB副控制台。

GPIO17/18的AT接线可以留着，但此独立demo不初始化它们。默认构建的USB AT查询固定为`AT`、`AT+CGMR`和`AT+MDUMPCFG?`。`CONFIG_ML307C_PROBE_ENABLE_DUMP_SAVE`默认关闭；显式开启后，确认固定模组版本和前述查询成功，再发送`AT+MDUMPCFG=1`并查询读回。模块USB重新枚举后同一次ESP32运行不重复执行该设置；ESP32重新启动该特定构建会再次执行。不会发模块重启命令或刷写模块固件。

诊断只读接收仅在VID/PID=2ECC:3012、接口4名称Mobile Diag Interface及IN端点0x82/64字节等实际描述符全部匹配时执行；没有向诊断OUT端点发送实时日志启用数据。USB AT探针也校验接口2名称及实际Bulk端点后才发送固定命令。

## 编译与使用边界

依赖已有ESP-IDF 5.4.3及ESP Python环境，无需新增通用工具或外部组件。输出放根目录`build/ml307c-usb-enumerate`，使用独立sdkconfig。不要用此demo生成的分区表、引导文件直接覆盖当前设备；临时安装及恢复应用须沿用项目现有完整备份和分区核验流程。

2026-11-25初版210256字节编译通过；首测设备描述符读取失败后，增加S3 USB端口寄存器只读观察，当前镜像210576字节，SHA256为`4ef9c3d59ec9526bbcb81b22dcac05a690def5674c811b7506abd1ca6fcf5cd1`。两次临时刷入均验证应用MD5和应用区外区域；当前审计为`build/voice-radar-flash-20261125-135936/device.json`。只读端口观察不修改USB控制寄存器或官方组件。

当前`flashed=true`，`hardwareVerified=false`、`enumerationPassed=false`。14:00:24 USB控制器观察到connected=1，复位完成后enabled=1、speed_code=2（low speed），随后`EP0 Error / CHECK_SHORT_DEV_DESC FAILED`，未取得VID/PID。证据：`build/ml307c-usb-enumerate/port-live-snapshot.json`。低速识别不符合4G模块USB正常工作预期，优先检查D+/D−方向及接点、丝印对应；尚不能认定当前手册丝印错误或模块损坏。需用户在断电后交换两根USB数据线作对照，其余连接保持，之后重新上电观察。此demo已运行，只读COM13日志采集仍持续。

以上为首次失败记录。14:03:46现场重新连接后速度变为full，首描述符请求仍失败；14:05重启ESP32主机后枚举成功，VID/PID=2ECC:3012。14:09进一步读取字符串描述符，返回Mobile RNDIS Network Adapter、Mobile Diag Interface、Mobile AT Interface。14:13再次枚举成功，打开接口4、IN端点0x82进行15秒只读采样，未收到字节；取消与接口释放完成，没有ESP32 panic。证据：`build/ml307c-usb-enumerate/strings-live-snapshot.json`、`build/ml307c-usb-enumerate/passive-live-snapshot.json`。

当前安装镜像218016字节，审计`build/voice-radar-flash-20261125-141216/device.json`，实际身份以`build/ml307c-usb-enumerate/identity.json`及`build/ml307c-at-test-firmware-20261125.json`为准。枚举已通过，诊断接口可打开，但完整日志抓取仍未通过。尚未启用日志、未取得模组内部崩溃原因，正式通话轮数仍为0。

14:25新增固定只读USB AT查询后，三个查询均立即成功：AT返回OK，CGMR返回ML307C-DL-CN-MBRH1S00，MDUMPCFG查询返回0。诊断接口45秒被动接收仍为0字节，取消和释放完成。当前已安装此版镜像220992字节，SHA256为`d74215522434612ed070e180df26eb4a1bbe1bc34eb043415db226e30eb14255`；刷入审计`build/voice-radar-flash-20261125-142418/device.json`，应用MD5及应用区外校验全部通过。证据：`build/ml307c-usb-enumerate/at-query-live-snapshot.json`。

现有两个商家RAR包及解压目录内均未找到CATStudio程序或匹配的DBG文件。已核对维护诊断手册第16页截图，Communication Settings确实支持Serial及Socket/TCP Client选项，可作为后续ESP32转发原始诊断数据的候选接入方式；是否存在额外封装需要实测，不能认为仅有此选项就保证兼容。缺少工具和DB的具体资料请求已整理到`tests/ml307c_diag_vendor_request.md`。

14:42按用户指出的维护诊断手册第19页启用死机Dump保存。配置前读回0，`AT+MDUMPCFG=1`返回OK，配置后查询返回`+MDUMPCFG: 1`；USB AT接口随后释放。45秒诊断只读窗口仍0字节，没有观察到Dump发生或新设备，因此没有Dump文件。该设置控制死机后的现场保存，不等于实时AP/CP日志开关。

当前安装专用开启版本221680字节，SHA256为`58d64f0dae0c65337f4343e09ebb4e322cc6d93c78ad4e39fe25dc25bf71b52a`；审计`build/voice-radar-flash-20261125-144151/device.json`，应用MD5及应用区外校验全部通过。证据`build/ml307c-usb-enumerate/dump-enable-live-snapshot.json`，模块设置独立记录`build/ml307c-usb-enumerate/module-dump-setting.json`。当前模块Dump保存已开启，诊断固件还不能通话；正式40轮仍0轮。发生故障后应保留并读取现场，再决定恢复，不应在未保存现场时盲目重启。

```powershell
$env:PATH = 'F:\Espressif\python_env\idf5.4_py3.11_env\Scripts;' + $env:PATH
. F:\Espressif\frameworks\esp-idf-v5.4.3\export.ps1
python "$env:IDF_PATH\tools\idf.py" -C tests/firmware/ml307c-usb-enumerate -B build/ml307c-usb-enumerate -D IDF_TARGET=esp32s3 -D SDKCONFIG="$((Get-Location).Path.Replace('\','/'))/build/ml307c-usb-enumerate/sdkconfig" reconfigure
ninja -C build/ml307c-usb-enumerate -j 2
```

正常枚举后只输出一次接口信息，诊断样本最多输出一包，不持续刷屏；USB掉线后输出掉线事件，并等待重新连接。掉线本身不能区分供电故障与模块内部重启。后续需要核对厂商专用日志激活命令和匹配的日志DB；不能假定拿到USB串口就能解码完整AP/CP日志。

## 官方依据

2026-11-25 14:58起实物已切换为[语音固件并行USB观察调试版](../ml307c-voice-usb-observer.md)，该目录的独立demo不再是当前运行镜像。后者保持UART通话，已完成一次90秒App呼入调试，双向音频数据正常；仍未捕获Dump或确认稳定性根因。真实当前镜像以`build/ml307c-at-test-firmware-20261125.json`为准。

- [ESP-IDF 5.4.3 USB Host说明](https://docs.espressif.com/projects/esp-idf/en/v5.4.3/esp32s3/api-reference/peripherals/usb_host.html)：S3可作USB主机，支持Full Speed和Low Speed。
- [ESP-IDF USB引脚映射](https://github.com/espressif/esp-idf/blob/v5.4.3/examples/peripherals/usb/README.md)：S3 D−=GPIO19，D+=GPIO20。
- [官方CDC Host组件](https://components.espressif.com/components/espressif/usb_host_cdc_acm)：支持CDC及具备指定Bulk端点的CDC-like厂商接口，不能据此保证ML307C诊断协议兼容。
- 用户提供的ML307C硬件设计手册：DBG UART默认115200、模块本体串口1.8V；DBG并非Tiny小板主RX/TX排针。Tiny手册将其列为测试点，实物位置尚未确认，不能直接把3.3V ESP32接到模组DBG引脚。
- 用户提供的ML307C维护诊断手册：完整AP/CP日志抓取流程使用电脑USB、CATStudio和匹配的DB。未提供已验证的ESP32诊断桥接方案。
