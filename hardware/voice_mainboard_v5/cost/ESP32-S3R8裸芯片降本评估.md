# 语音对讲主板：ESP32-S3R8裸芯片降本评估

2026-11-23。此文件是候选评估，尚未替换V5 PCB、BOM或固件，也没有把候选预算写成已完成主板报价。

## 结论

语音对讲通过ML307走4G，不需要Wi-Fi和蓝牙通信。可以评估将ESP32-S3-WROOM-1-N8R8模组改为ESP32-S3R8裸芯片、外接8MB Flash及必要外围。ESP32-S3各型号的Wi-Fi和蓝牙射频已集成在SoC内部，没有以去除无线射频为区别的ESP32-S3型号。裸芯片方案的成本差来自减少模组PCB、封装集成及模组上的外围采购成本，不能理解成拿掉独立的发射芯片。

## 当前项目对存储的需求

- `sdkconfig`配置8MB Flash，`partitions.csv`设置两个0x380000的OTA应用分区，末尾至0x712000。不能直接换成4MB Flash并保留当前分区。
- 已启用八线PSRAM、启动初始化及外部内存分配，未开启忽略PSRAM缺失；mbedTLS分配到外部内存。音频包含AEC/AFE与Opus。裸芯片候选保留8MB PSRAM，避免同时变更音频和内存方案。
- 蓝牙配置关闭。Wi-Fi组件仍在编译配置中，源码主网络初始化使用`Network4g::init`和ML307 AT接口。此次没有删除Wi-Fi组件或改动通信协议；组件禁用是否影响MAC读取、依赖及链接需独立检查。

## 型号区别

| 型号 | 封装内Flash | 封装内PSRAM | 本项目候选意义 |
|---|---|---|---|
| ESP32-S3R8 | 无 | 8MB、Octal SPI、3.3V存储接口 | 优先候选，需外接8MB Flash |
| ESP32-S3FN8 | 8MB、Quad SPI | 无 | 仍需PSRAM，不能按R8直接套用 |
| 无后缀ESP32-S3 | 无 | 无 | 两种存储都需外接 |
| 当前WROOM-1-N8R8模组 | 模组含8MB | 模组含8MB | 已有布局和外围基线 |

芯片型号依据乐鑫官方ESP32-S3 Series Datasheet v2.2，Table 1-1，PDF第13页：
https://www.espressif.com/sites/default/files/documentation/esp32-s3_datasheet_en.pdf

## 本次数量阶梯

正常访问立创商城公开搜索页读取服务器页面自带的`productPriceList`，日期2026-11-23。价格是采购单价，不是已验证的新PCB整单报价。

| 器件 | 商城编号 | 100个档（元） | 1000个档（元） |
|---|---|---:|---:|
| ESP32-S3R8裸芯片 | C2913194 | 13.50 | 12.65 |
| GD25Q64ESIGR Flash候选，64Mbit＝8MB | C2831359 | 4.05 | 2.60 |
| **裸芯片＋Flash小计** | — | **17.55** | **15.25** |
| 当前ESP32-S3-WROOM-1-N8R8 | C2913201 | 21.51 | 20.56 |
| **未计新增外围之前的差额** | — | **3.96** | **5.31** |

参考库存：R8为15977个、GD25Q64ESIGR为47968个。库存会变化。GD Flash目前只作为价位和容量匹配的候选，精确数据手册、时序、电压、ESP-IDF驱动/QE位及封装尚待核对和实测。原检索的W25Q64JVSSIQ库存不足且价格较高；不能将它作为此次低价量产的默认料号。

来源：
- ESP32-S3R8：https://item.szlcsc.com/3198292.html
- GD25Q64ESIGR：https://item.szlcsc.com/2984987.html
- 当前模组：https://item.szlcsc.com/3198299.html
- 本次精简阶梯记录：[esp32-s3-bare-candidate-prices.json](jlc-100/esp32-s3-bare-candidate-prices.json)

## 改板所需工作

裸芯片使用QFN-56 7×7mm与底部地焊盘，不能替换到WROOM模组的焊盘上。需要重做芯片与存储区域布线，保持现有GPIO功能，核对芯片GPIO编号、封装脚号、存储占用、BOOT和EN。

保留外接40MHz晶振和适配负载电容、芯片各电源域供电与去耦、Flash供电及走线。官方硬件指南明确要求40MHz晶振，并要求所有芯片电源域供电，不能因不启用无线而不接模拟电源引脚。Wi-Fi/蓝牙无线功能不需要启用；天线和RF外围的取消应纳入最终硬件核查。

官方指南：
https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/schematic-checklist.html

新增晶振、阻容、Flash及裸芯片封装对应的贴装/钢网和布线费用尚未锁定。因此1000台每台净节省不能直接记为7.91元（模组20.56减裸芯片12.65）；即使只计两项，差额也已变为5.31元，新增外围还要继续从差额扣除。

当前1000台同口径条件预算68.5035元/台，替换芯片＋Flash后、尚未补新增外围时的数学小计是63.1935元/台。它不是新的完整主板报价，也不是已达到50元目标。

原理图/PCB设计后需补电源与时钟、Flash/PSRAM启动及压力测试、音频AEC/Opus和4G长通话、掉电/OTA与烧录验证。当前协议和主动丢旧包策略维持项目约定。
