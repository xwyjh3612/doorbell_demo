# GPIO5/8雷达独立测试固件

当前版本`rx5-uart-2`，ESP-IDF 5.4.3，ESP32-S3。用于雷达接GPIO5/8、电脑接板载CH343 UART口的对照测试；可在运行时换GPIO6或GPIO8接收，保存最近512字节供延后读取。语音对讲应用及其协议不变。

当前设备已通过控制台切到GPIO6/115200，等待雷达TX由GPIO5改接GPIO6；重启会恢复GPIO5默认值。当前配置及验证结果见[TEST_RESULTS.md](TEST_RESULTS.md)。

| 雷达 | ESP32-S3 |
|---|---|
| TX | GPIO5，UART2接收 |
| RX | 可接GPIO8，本程序将GPIO8保持输入、不发送；也可悬空 |
| 5V | 稳压5V供电 |
| GND | 共地 |

电脑接标记UART的USB接口，当前设备为CH343 COM13，日志115200。每次上电默认雷达接收GPIO5、115200、8N1。此版不支持把雷达改到GPIO43/44，它们是控制台及下载线路。

当前语音工程实际使用`CUSTOM_AUDIO_BOARD`：麦克风GPIO12/13/14、功放GPIO7/15/16，4G用UART1及GPIO17/18、DTR GPIO4，按钮GPIO0。GPIO5/8在该配置中未被占用，雷达可用UART2。需要给雷达发查询命令时再单独配置GPIO8发送，本程序没有发送功能。

## 采集

```powershell
python examples/radar_gpio5_demo/capture.py --port COM13 --passive --seconds 40 --output build/radar-gpio5.log
```

`--passive`只读日志，不清计数、不改配置；脚本会检查CH343 USB标识，读取`RADAR_GPIO5`日志确认运行程序。去掉该参数会通过ESP32控制台配置指定接收引脚/波特率并清零，命令不会从GPIO8发往雷达。支持`radar status`、`radar clear`、`radar baud 115200`、`radar raw on/off`、`radar rx 5/6/8`及其他接收波特率，不能切到控制台引脚。

`radar history`读取所选接收引脚最近512字节，按从旧到新排列；`last_ms`是最近一次接收在ESP32启动后的毫秒数，不是读取时刻。即使电脑未打开串口，数据也会保留到被后续字节覆盖、切换引脚/波特率、clear或重启。数据可能从半帧开始，仍需按帧头、长度、帧尾及校验重组，不能把保存日志当作本轮新增数据。

```powershell
# 不清计数和改配置，在采集开始及结束读取已保存数据
python examples/radar_gpio5_demo/capture.py --port COM13 --passive --history --seconds 40 --output build/radar-gpio-history.log
```

换引脚时只把雷达TX移到所选GPIO，雷达RX继续悬空或接未驱动的GPIO8。若选GPIO8接收，必须先拔下原雷达RX→GPIO8那根线，再把雷达TX接过去。GPIO6/8均未被当前语音配置占用；是否实际能收到有效帧仍需接线对照验证。

`bytes`包含所有接收字节，`header5359`只是报文头候选计数；完整有效帧需另行检查长度、帧尾和校验。原始日志最多512字节/秒，状态每3秒输出。有人/无人按状态变化上报，一段时间没有新消息不能单独当作串口故障。

## 编译与app烧录

激活ESP-IDF后进入本目录运行`idf.py build`。本机click依赖临时目录的用法见[GPIO44 demo文档](../radar_pin_demo/README.md)。

只在确认雷达数据线接GPIO5/8、未接GPIO43/44后执行烧录。先核对同一设备、分区表和OTA槽位并备份当前app，只写已确认的`ota_0/0x10000`。不要全量flash、擦除Flash或覆盖NVS/引导/OTA记录。

```powershell
# 从主项目根目录；先完成设备核对及备份
python -m esptool --chip esp32s3 --port COM13 --baud 460800 write_flash 0x10000 examples/radar_gpio5_demo/build/radar_gpio5_demo.bin
```

实测及备份信息见[TEST_RESULTS.md](TEST_RESULTS.md)。
