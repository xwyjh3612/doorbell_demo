# 独立引脚诊断demo验证记录

设备后续已改烧`rx5-uart-1`，默认GPIO5接收、COM13输出日志。GPIO44版的有效报文记录保留在本文，当前设备状态和GPIO5对照结果见[GPIO5验证记录](../radar_gpio5_demo/TEST_RESULTS.md)。

## GPIO5对照测试准备

用户询问是否换GPIO5/8及后续选口。核对实际语音配置：`main/settings.h`选择`CUSTOM_AUDIO_BOARD`，麦克风GPIO12/13/14、功放GPIO7/15/16；4G用UART1、GPIO17/18及DTR GPIO4，按钮GPIO0。当前配置未占用GPIO5/8，因此推荐雷达UART2的RX=GPIO5、TX=GPIO8（需要查询命令时再启用发送），避开UART0与CH343共享线路。

通过COM14控制台将运行时接收改为GPIO5、115200，命令响应正常，随后清零观察6秒：0字节、0错误、GPIO5瞬时电平0。此时尚未确认用户已把雷达TX改接GPIO5，属于配置准备，不能判定GPIO5接收测试失败。没有烧录、复位或发送雷达命令，结束后关闭COM14；日志`build/radar-rx44-flash-20261119-103704/native-usb-rx5-prewire.log`。

**当前运行时监听GPIO5/115200；ESP32重启仍恢复固件默认GPIO44/115200。** 下一步雷达TX从板上RX改接GPIO5、雷达RX暂时悬空，供电及原生USB保持；当前只接收demo没有启用GPIO8发送。接好后抓取原始有效帧，与已验证GPIO44接收结果对照。

## 2026-11-19 已接线：收到有效雷达上报

用户明确确认雷达数据线均已接回：雷达TX→ESP32板上RX/GPIO44，雷达RX→板上TX/GPIO43。电脑通过原生USB COM14连接，运行`rx44-1`独立demo，UART2接收115200、8N1；应用不驱动GPIO43，不发送雷达命令。

初次状态为累计30字节、3个头部候选、0错误，这是此次采集前累计值。重新配置并清零后连续采集40秒，实际新增30字节，抓到以下3条原始报文：

| ESP32日志时间（ms） | 原始报文 | 按R24DVD1手册解释 |
|---|---|---|
| 250915 | `53 59 05 01 00 01 0f c2 54 43` | 初始化完成 |
| 251015 | `53 59 80 01 00 01 00 2e 54 43` | 无人 |
| 251795 | `53 59 80 01 00 01 01 2f 54 43` | 有人 |

离线逐条验证帧头`53 59`、长度字段`0001`、总帧长10字节、帧尾`54 43`及8位累加校验；3帧全部通过，校验值分别为`c2`、`2e`、`2f`。UART错误0，最后一次有效上报为有人。

字段参考[R24DVD1用户手册V1.6](https://github.com/blakadder/berry-drivers/blob/main/R24D/datasheet/R24DVD1_User_Manual_V1.6%20en-US.pdf)：PDF页13–14为帧结构与校验，页16为初始化完成上报，页18为存在状态`00=无人/01=有人`及状态变化上报。捕获报文与这一协议一致；尚未读取完整产品型号或固件版本。

原始日志：主项目`build/radar-rx44-flash-20261119-103704/native-usb-connected-rx44.log`。采集结束后关闭COM14，没有复位、烧录或发送雷达命令。设备记录`device.json`已保存验证结果。

**结论：现在GPIO44/115200的雷达接收链路已通，初始化及无人→有人上报已验证。** 有人/无人按状态变化上报，不能仅根据短时字节计数不增长认定断线；本次没有观察到活动/体动周期数据。此次为一次初始化和存在状态变化验证，不能替代长期稳定性、检测准确率或呼吸心率验证。CH343物理隔离条件未确认，当前能收到有效帧也不证明长期没有共享线路干扰。

## 2026-11-19 原生USB及新版运行验证（接线确认前）

用户换USB接口后，电脑枚举原生USB Serial/JTAG COM14，标识`303A:1001`、序列号`AC:A7:04:EF:DB:F8`，CH343 COM13不再枚举。通过COM14观察到`RADAR_PIN`状态日志，确认新版运行；控制台命令`radar rx 44`、`radar baud 115200`、`radar raw on`、`radar clear`及`radar status`均响应正常。

初次连接时累计31字节、UART错误0、`header5359=3`、GPIO44电平1，但没有对应原始数据，不能认定为已校验的雷达帧或本次新增数据。设置并清零后观察约12秒，新增字节0；随后不发送命令再被动监听40秒，13条状态日志均为`rx=44 baud=115200 bytes=0 errors=0 header5359=0 level=1`，没有`RAW`日志。两次结束后均关闭串口，没有复位或烧录。

日志保存在主项目`build/radar-rx44-flash-20261119-103704/native-usb-first.log`及`native-usb-passive-105320.log`。本轮确认新版运行、原生USB控制台及配置命令可用；尚未收到可验证的完整雷达上报。

之前要求用户两根雷达数据线保持断开，用户本轮只确认已换USB接口，尚未明确是否接回数据线；因此0字节不能作为雷达已连接条件下的失败结论。CH343 USB不枚举也不能证明其TX物理高阻，GPIO44共享线路条件仍待核对。

## 2026-11-19 rx44-1实际烧录

用户确认已拔下雷达TX/RX数据线后执行。COM13设备为ESP32-S3 v0.2、MAC `ac:a7:04:ef:db:f8`，物理Flash 16MB，现有工程分区使用前8MB。

烧录前重新读取前8MiB Flash，保存至主项目`build/radar-rx44-flash-20261119-103704/before-flash-8MiB.bin`，SHA256：`23af00f3b7a694a0360b5bef949074293c0414e4fdbe84b302908a106d22339d`。该文件包含配置数据，仅本地保存，不提交Git。原始语音固件备份仍保留。

使用ESP-IDF分区解析器验证实际分区表及校验，与新demo布局一致；OTA记录copy0的seq=1、state=VALID、CRC有效，copy1为空，启动槽位为`ota_0/0x10000`。当前旧app为`radar_uart_demo/e751f18-dirty`，已提取完整ota_0备份`before-rx44-ota0.bin`，SHA256：`13618ecf52f29a0e77e2415d0ec247070af450973a6adeea93683cc4e5491181`。

仅写`radar_rx44_115200.bin`到`0x10000`，实际擦除范围`0x10000–0x4ffff`。烧录工具Hash校验通过；再次读取设备上的app描述信息，确认为`radar_pin_demo/rx44-1`，设备app MD5与本地镜像一致。

通过设备Flash MD5与烧录前备份比较，下列区域完全一致：`0x0–0xffff`（引导、分区、NVS、phy），`0x50000–0x38ffff`（本次写入扇区之后的ota_0），`0x390000–0x7fffff`（ota_1、OTA记录及剩余前8MiB）。上半部分物理Flash未访问。

雷达数据线保持断开，复位后通过COM13捕获引导日志，确认`Loaded app from partition at offset 0x10000`以及`cpu_start: Multicore app`。日志保存在同目录`boot-uart0.log`，备份及设备校验记录在`device.json`。

**当前新固件已经烧录，不再运行旧GPIO5 demo。** 仍只有CH343 COM13和两个蓝牙串口，尚无原生USB端口；尚未观察到新版`READY`、验证CLI或接收雷达数据。下一步保持雷达数据线断开，电脑USB线改接开发板原生USB口，待端口枚举后检查日志。接回GPIO44前仍需核对CH343发送端共享线路。

## rx44-1编译记录（烧录前）

用户确认接线为雷达TX→开发板丝印RX/GPIO44，雷达RX→丝印TX/GPIO43，并要求重新制作测试固件。当前版默认接收已由GPIO43改为GPIO44，115200、8N1；GPIO43在应用中保持输入，不向雷达发送命令，控制台为原生USB Serial/JTAG。下方初版GPIO43构建记录为历史结果。

- `idf.py build`成功，项目版本`rx44-1`，app大小261888字节（`0x3ff00`），分区容量检查通过。
- `esptool image_info --version 2`确认ESP32-S3、8MB/DIO/80MHz镜像，app版本`rx44-1`，Checksum与Validation Hash有效。
- app SHA256：`3fe4f531ab8da0aa192b884b88830a443843d3667dc7134bc192f40dfaf4f7ab`。
- 固件已复制到主项目`outputs/radar-firmware-20261119/radar_rx44_115200.bin`，复制后SHA256一致。
- 采集脚本语法检查通过，默认接收引脚同步改为GPIO44；生成配置仍为原生USB主控制台、无第二控制台、无UART0控制台。
- 电脑仍仅枚举CH343 COM13及两个蓝牙串口，没有原生USB端口。本次没有打开串口、复位、读取Flash或烧录，雷达数据线仍连接GPIO44/43。

尚未验证新版启动、CLI或雷达数据。下一步先断开雷达数据线完成设备核对、备份和app烧录；日志需连接原生USB。GPIO44与CH343发送端共享仍需硬件核对及隔离，改默认引脚不能消除外部发送端影响。

## 2026-11-19 编译与采集脚本验证

- ESP-IDF 5.4.3、ESP32-S3，`idf.py build`成功。app大小261760字节（`0x3fe80`），小于`ota_0`的`0x380000`，分区容量检查通过。
- `esptool image_info`确认镜像Checksum和Validation Hash有效。
- app文件SHA256：`c36a00dd2cb985478214f820cda850dc6c36f852ef5e5be304799b3144c650fb`。
- 生成配置确认主控制台为USB Serial/JTAG、无第二控制台、`ESP_CONSOLE_UART_NUM=-1`；雷达接收为UART2，默认GPIO43、115200、8N1，无发送引脚映射。
- `capture.py`通过Python语法编译。实测传入COM13时，因USB标识为CH343而在打开串口前退出，无命令发送。
- 原语音固件备份`build/radar-before-demo-ota0.bin`和前8MiB备份`build/radar-before-demo-flash.bin`的SHA256与原记录一致。

本机IDF Python环境的click为8.3.1，不满足IDF的`click<8.2`约束；构建使用主项目`build/idf-python-deps`中的click 8.1.8，通过当前进程的PYTHONPATH加载，没有降级现有全局依赖。

## 初版硬件实测进度（GPIO43，尚未烧录）

本轮尚未烧录新demo，也未获得新的雷达数据。电脑仅枚举CH343 COM13及两个蓝牙串口，尚无原生USB Serial/JTAG端口。

用户此前将雷达接到开发板丝印TX/RX，旧demo仍在GPIO5接收，因此不能根据旧demo的0字节判断此次接线是否有效。新demo烧录前，需要先断开雷达两根数据线；烧录时重新核对设备、分区与启动槽位并备份当前app，只写已确认的app分区。

烧录完成后从开发板原生USB口看日志，待`READY`后接雷达TX到GPIO43，雷达RX悬空，5V供电并共地。运行采集脚本观察原始字节。GPIO44仅用于板载CH343 TX已物理隔离的条件；软件更换控制台不能隔离外部发送端。

当前验证只证明可编译及采集脚本的串口选择保护生效，尚未验证设备启动、CLI运行或雷达接收。`header5359`只统计头部候选，不代表完整校验帧或有人状态。

### TX接TX后的被动监听

用户报告雷达TX直接接开发板丝印TX。电脑仍仅枚举CH343 COM13及两个蓝牙串口，无原生USB端口。以115200、8N1打开COM13被动监听12秒，接收0字节；没有发送任何串口数据、请求复位或烧录，结束后关闭串口。日志：主项目`build/radar-pin-txtx-passive-20261119.log`。

CH343接收端通常与GPIO43相连，可被动观察该节点，但尚未烧录新版，旧应用的UART0输出仍可能占用GPIO43。因此此次0字节不能判断雷达是否正常，也不代表新版GPIO43输入方案已测试。后续先断开雷达数据线，再烧录新版、连接原生USB并确认`READY`，然后接入雷达TX。

### 用户报告可能掉电后复查

用户表示之前可能是电源线掉了，要求再次检查。未确认是哪根电源线，也未测量模块供电。本次以115200、8N1被动监听COM13约40秒，没有发送命令、请求复位或烧录，结束后关闭串口。

收到560字节，全部是旧demo的8条周期状态日志：`RADAR: STATUS baud=115200 bytes=102 errors=0 RX_level=0`。雷达累计字节数全程保持102，没有新增接收字节，也没有原始十六进制数据。102为连接前累计计数，不能判断为有效雷达帧。日志：`build/radar-txtx-power-recheck-20261119-101752.log`。

本次确认ESP32旧demo及CH343日志通路可用；旧demo仍映射GPIO5，日志中的电平0也是GPIO5，不是现在TX接TX的GPIO43。尚不能确认雷达供电或TX输出，也未验证新版接线。
