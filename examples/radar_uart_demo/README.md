# R24D 雷达串口读取 demo

独立 ESP-IDF 5.4 项目，目标 ESP32-S3，不启动语音对讲、4G、MQTT 或音频。只读取雷达原始串口数据，不发送模块配置命令，也不修改主项目的官方通话协议。

## 接线

| 雷达 | ESP32-S3 |
|---|---|
| RX | GPIO8（UART2 TX） |
| TX | GPIO5（UART2 RX） |
| 5V | 稳压 5V |
| GND | GND（共地） |

GPIO4 是语音对讲主项目的 4G DTR，不用于雷达。雷达信号需为 3.3V 电平；5V UART 信号需要电平转换。右侧 3.3V、SWD/SWC、GP 引脚留空。

## 编译与读取

在 ESP-IDF 5.4 终端中进入本目录：

```powershell
idf.py set-target esp32s3
idf.py build
```

串口监视器使用 **115200、8N1**。雷达 UART2 默认 **9600、8N1**，两者波特率独立。

2026-11-19资料核对：用户照片中的R24D外观与R24DVD1参考板一致，该系列资料为**115200、8N1**，应优先用`radar baud 115200`。原demo的9600默认值来自另一型号资料，尚未修改固件默认值。不同型号的协议、供电和排查证据见[排查资料.md](排查资料.md)。

```text
radar status
radar baud 115200
radar baud 9600
radar raw off
radar raw on
```

支持雷达波特率：9600、19200、38400、57600、115200、256000。`radar baud` 仅改变 ESP32 接收配置，不发送任何数据给雷达。切换时清空输入缓冲和统计计数。

默认打印十六进制 UART 读取片段，每 5 秒打印接收字节数与 UART 错误数。片段不等于完整协议帧。原始日志限流到每秒 512 字节，计数包含全部读取字节。持续出现乱码或帧错误时检查波特率、电平和共地；字节数始终为 0 时检查供电、雷达 TX→GPIO5 与模块是否主动上报。

可以保存日志：

```powershell
python capture.py --port COM13 --seconds 30 --reset --output build/radar-9600.log
python capture.py --port COM13 --seconds 30 --radar-baud 115200 --output build/radar-115200.log
python capture.py --port COM13 --scan --seconds 8 --output build/radar-scan.log
```

`--scan` 在六个波特率下各观察指定秒数，不会写入雷达参数，最后停留在 19200。完成后可用 `radar baud 9600` 恢复默认值。状态中的 `RX_level` 是 GPIO5 的瞬时电平，不能单凭它判断模块是否正常。

接收成功后才根据确认的模块协议解析“有人/没人”；这个 demo 不把任意字节猜测成人体状态。

## 烧录与恢复

本 demo 使用主项目的 `../../partitions.csv`。对于已有语音对讲应用的板子，烧录前先备份 Flash，核对**设备实际分区表及 OTA 启动槽位**，仅将 demo app 写入当前启动 app 槽位。不要直接使用 `erase-flash` 或默认全套 `flash` 覆盖已有分区和 OTA 数据。

本次板上备份保存于主项目忽略的 `build/radar-before-demo-flash.bin`，不提交 Git。恢复时使用备份中同一 app 槽位的原固件，只恢复被 demo 覆盖的 app 区域；保留现有 NVS、OTA 数据和引导程序。首次使用的空白板可以常规 `idf.py -p <COM口> flash monitor`。

本次 COM13 设备已核对启动槽位为 ota_0，地址 `0x10000`。原应用已提取到主项目 `build/radar-before-demo-ota0.bin`，备份校验信息见 `build/radar-demo-device.json`。**仅适用于这次备份的同一块板、且其分区和启动槽位未变更时**，在主项目根目录恢复：

```powershell
python -m esptool --chip esp32s3 --port COM13 --baud 921600 write_flash 0x10000 build/radar-before-demo-ota0.bin
```

demo 编译日志保存在主项目 `build/radar-demo-build.log`，原始接收日志保存在主项目 `build/radar-demo-*.log`。
