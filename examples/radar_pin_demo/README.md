# R24D独立引脚诊断demo

ESP-IDF 5.4，ESP32-S3。与语音对讲应用隔离，不启动4G/音频/MQTT，不改变通信协议，不向雷达发送命令。

当前固件`rx44-1`见[固件目录](../../outputs/radar-firmware-20261119/README.md)。默认监听板上RX/GPIO44，已烧录并完成镜像回读校验；COM14原生USB日志及配置命令正常，已抓到通过校验的初始化完成、无人及有人上报，见[验证记录](TEST_RESULTS.md)。

## 为什么重写

旧demo固定从GPIO5接收，换到板上TX/RX并不会改变软件映射。当前`rx44-1`版用原生USB Serial/JTAG作为控制台，UART2只接收，默认GPIO44（板上RX）、115200、8N1；可在GPIO43、44、5间切换。波特率匹配R24DVD1参考资料，模块完整型号及固件尚未读到。

板载CH343通常连接UART0：其RX输入连接ESP32 GPIO43（板上TX），其TX输出连接GPIO44（板上RX）。把日志移到原生USB，只能消除ESP32应用的UART0输出，不能断开CH343的物理连接；拔掉CH343 USB线也不保证其发送端高阻，取决于开发板供电设计。

## 当前默认接线：GPIO44只接收

先断开雷达数据线完成烧录，再用原生USB连接电脑。**接入雷达TX前先确认CH343 TX与GPIO44物理隔离，或使用没有这条共享线路的开发板。** 仅换USB口、改软件不能保证CH343发送端高阻。

| 雷达 | ESP32-S3 |
|---|---|
| TX | 板上标RX的针，GPIO44 |
| RX | 建议悬空；若仍接板上TX/GPIO43，本应用也不会发送 |
| 5V | 稳压5V |
| GND | 共地 |

应用将GPIO43保持为输入，GPIO44通过GPIO矩阵连接UART2接收端，不输出UART0日志。用户当前雷达TX→板上RX、雷达RX→板上TX的方向正确；GPIO44与外部CH343发送端共用是需要单独核对的硬件条件。若无法隔离CH343，可改用下面的GPIO43台面诊断或独立GPIO5。

## 可选测试接线：GPIO43只接收

先断开雷达数据线，完成烧录并启动；电脑连接标记USB的原生USB接口，等控制台出现`READY`，执行`radar rx 43`后才连接雷达TX。

| 雷达 | ESP32-S3 |
|---|---|
| TX | 板上标TX的针，GPIO43；本程序将其重映射为输入 |
| RX | 悬空 |
| 5V | 稳压5V |
| GND | 共地 |

看似TX接TX，是因为板上丝印代表默认功能，本程序已把GPIO43配置为接收输入。CH343在此节点是输入端，应用启动后不产生发送端相连问题。

**ESP32 ROM/已有引导程序在启动和下载阶段仍可能通过GPIO43发送日志。** 所以数据线应在应用`READY`后接入，重新启动/烧录前断开；此诊断设计用于台面测试，不作为长期产品接线。原生USB使用GPIO19/20，不能接其他外设。

## 切换独立引脚

`radar rx 5`支持原来的独立GPIO5输入，用于对照；此前GPIO5测试未收到持续雷达数据，并未证明该接收通路稳定。更改运行时设置后保持到ESP32重启，重启恢复GPIO44/115200。

后续接入当前语音配置推荐UART2 RX=GPIO5、TX=GPIO8：实际`CUSTOM_AUDIO_BOARD`和4G配置未占用这两个引脚，能避开下载串口共享线路。当前demo只接收，切到GPIO5后雷达TX接GPIO5、雷达RX暂时悬空，GPIO8只作后续发送预留。GPIO5的新demo硬件对照测试尚未完成。

## 命令和输出

```text
radar status
radar rx 44
radar rx 43
radar rx 5
radar baud 115200
radar baud 9600
radar raw on
radar raw off
radar clear
```

`bytes`包含全部接收字节，`errors`计FIFO/缓冲溢出、帧/奇偶错误和读错误。`header5359`只统计53 59相邻字节候选，跨UART片段累计，不是已通过校验的完整雷达帧，不能当作有人/无人。原始十六进制日志最多512字节/秒，每3秒状态输出接收引脚、波特率和瞬时电平。

实际捕获的`53 59 80 01 00 01 00 2e 54 43`为无人、`53 59 80 01 00 01 01 2f 54 43`为有人，均已离线核对长度和累加校验。固件本身仍只输出原始数据与头部候选，并未加入实时完整帧解析。参考手册的有人/无人消息按状态变化上报，状态不变时没有这类新消息是正常的；串口日志采集前的累计计数没有对应原始字节时不能当作已验证消息。

## 编译和烧录

在ESP-IDF 5.4环境中：

```powershell
idf.py build
```

本机ESP-IDF位于`F:\Espressif\frameworks\esp-idf-v5.4.3`。若激活时提示`click<8.2`不满足，可从主项目根目录使用临时依赖目录，不改全局Python依赖：

```powershell
$env:IDF_TOOLS_PATH = 'F:\Espressif'
$env:PATH = 'F:\Espressif\python_env\idf5.4_py3.11_env\Scripts;' + $env:PATH
python -m pip install --target build/idf-python-deps 'click==8.1.8'
$env:PYTHONPATH = (Resolve-Path build/idf-python-deps).Path
. 'F:\Espressif\frameworks\esp-idf-v5.4.3\export.ps1'
Set-Location examples/radar_pin_demo
idf.py build
```

编译验证和硬件实测进度见[TEST_RESULTS.md](TEST_RESULTS.md)。

当前测试板此前已备份前8MiB Flash，启动槽位记录为ota_0/0x10000。**烧录前先断开雷达数据线，再重新核对同一设备、分区表、OTA槽位并备份当前app**。仅写当前app，不覆盖引导、NVS、分区表或OTA选择，不使用默认全量`flash`。

如果重新核对后还是同一块板、同一槽位，可在主项目根目录写入此app：

```powershell
python -m esptool --chip esp32s3 --port <可用烧录COM口> --baud 460800 write_flash 0x10000 examples/radar_pin_demo/build/radar_pin_demo.bin
```

写完把电脑USB线接到开发板原生USB口，等待新的COM口枚举。CH343的COM13不是本demo控制台。

```powershell
python examples/radar_pin_demo/capture.py --port <原生USB COM口> --rx 44 --radar-baud 115200 --seconds 40 --output build/radar-pin-44.log
```

本程序的`capture.py`只用于新demo原生USB控制台，不要在雷达接UART0时把它对COM13运行，否则CLI文字可能进入雷达。

采集脚本会先检查USB设备标识`303A:1001`，再等待新demo的`RADAR_PIN`状态日志；两项均匹配后才发送ESP32控制台命令。误选CH343串口会直接退出，不发送文字。

## 接收通路检查

先从雷达拔掉TX信号线，再用仍连着选定接收引脚的那根线接ESP32 GND，观察`level`应为0。避免将雷达输出直接接地，不接5V。该检查只验证数字输入低电平和接地通路，不证明UART高速收发或雷达工作正常。

若新demo也始终0字节，应测模块端供电并用独立USB转TTL/逻辑分析仪检查TX实际波形；不能靠重复换GPIO或发热确定雷达正常。
