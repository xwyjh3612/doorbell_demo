# GPIO44雷达接收测试固件

此目录包含以下独立app版本：

| 文件 | 雷达接收 | 日志接口 |
|---|---|---|
| `radar_rx44_115200.bin`（`rx44-1`） | GPIO44，板上RX | 原生USB COM14 |
| `radar_rx5_115200_uart.bin`（`rx5-uart-1`） | GPIO5 | CH343 UART COM13 |
| `radar_gpio_switch_115200_uart_v2.bin`（`rx5-uart-2`） | 默认GPIO5，支持GPIO6/8，保存最近512字节 | CH343 UART COM13 |

测试板目前已烧录`rx5-uart-2`并在运行时切到GPIO6/115200，等待改接雷达TX，其实测进度见[GPIO5验证记录](../../examples/radar_gpio5_demo/TEST_RESULTS.md)。新版大小264672字节，SHA256：`8c369446c785ed413a82467d7a5d9b31138d37773f0af78a96853623d602e765`；`rx5-uart-1`保留用于恢复，大小264224字节，SHA256：`ac3926f4b3151065e8ed96a6a424d01a3e5ae3a19281f2c0ba34e38045221c76`。两个版本均不向雷达发送命令。下文为保留的GPIO44版本信息。

文件：`radar_rx44_115200.bin`，独立ESP32-S3 app，版本`rx44-1`，ESP-IDF 5.4.3。

- 接收：UART2，GPIO44（开发板丝印RX），115200、8N1，匹配雷达TX→ESP32 RX接线。
- 发送：不配置发送引脚；GPIO43（开发板丝印TX）在应用中保持输入，不向雷达RX发送。
- 日志及命令：原生USB Serial/JTAG（GPIO19/20），不能使用CH343 COM13查看应用日志。
- 内容：原始字节、UART错误、瞬时输入电平、53 59头部候选计数。没有经过完整校验的有人/无人或生命体征解析。
- 范围：仅独立雷达诊断，不启动4G或音频，不修改语音对讲协议。

已完成编译、分区容量及镜像校验。2026-11-19已烧录到原测试板`ota_0/0x10000`，回读app版本及设备镜像校验通过，未写区域与备份一致；原生USB COM14日志及配置命令正常。已抓到初始化完成、无人及有人3条完整雷达报文，长度、帧尾及累加校验均通过，GPIO44/115200接收链路已验证可用。此次未验证长期稳定性或呼吸心率，详情见[验证记录](../../examples/radar_pin_demo/TEST_RESULTS.md)。

大小：261888字节（`0x3ff00`）。SHA256：`3fe4f531ab8da0aa192b884b88830a443843d3667dc7134bc192f40dfaf4f7ab`。

## 烧录条件

烧录前断开雷达TX/RX数据线，避免雷达TX与CH343下载输出同时连接GPIO44。原记录设备为ESP32-S3、MAC `ac:a7:04:ef:db:f8`，启动分区`ota_0`、偏移`0x10000`、容量`0x380000`；每次烧录前重新读取确认设备、分区表、OTA选择并备份当前app。

这是app镜像，不能烧在`0x0`，不需要覆盖引导程序、分区表、NVS或OTA选择。仅在重新确认仍为上述设备和槽位之后，从项目根目录执行：

```powershell
python -m esptool --chip esp32s3 --port <烧录COM口> --baud 460800 write_flash 0x10000 outputs/radar-firmware-20261119/radar_rx44_115200.bin
```

烧录后用开发板原生USB口看日志。接入雷达TX前，核对并隔离CH343 TX与GPIO44共享线路；拔掉CH343 USB线不保证芯片发送端高阻。如无法隔离，可保持雷达数据线断开，通过原生USB执行`radar rx 5`后把雷达TX接到独立GPIO5，避免共享线路。

完整接线、GPIO43可选诊断和原固件恢复说明见[demo文档](../../examples/radar_pin_demo/README.md)。
