# ESP32-S3语音固件

- `voice.bin`：基础语音版，关闭可选人体存在雷达，不编译雷达接收模块。
- `voice-radar.bin`：语音＋R24D人体存在检测版，UART2、GPIO6接收、115200，GPIO8不驱动。
- `voice-radar60.bin`：语音＋R60ABD1 60GHz版，增加呼吸、心率、体动及距离，接线同24G版。
- 对应JSON：编译时间、应用镜像长度、SHA256及变体配置。

2026-11-20 BOOT 接听更新：待机短按 BOOT/GPIO0 呼出，设备来电时短按接听；连接中和通话中忽略按键。消抖及松开重按保护避免重复触发，接听沿用原 `cmd answer` 路径。当前设备的 60GHz 版本已按此逻辑重新构建；其他变体如需此功能应使用当前源代码重新构建。

当前 COM13 设备已刷入该 60GHz 应用镜像，镜像校验和应用以外区域校验通过；重启后 MQTT 在线、GPIO0 上拉输入、雷达接收正常，无 panic。主机测试覆盖 11 个通话场景及原有 OTA/UDP/雷达回归。实体 BOOT 按压及通话听感未由自动化验证，须在 App 呼叫时按板上的 BOOT 进行实际操作。记录见 [boot-answer-verification.json](boot-answer-verification.json)。

生成命令：项目根目录的`tools/build-firmware.ps1 -Variant voice`、`-Variant voice-radar`或`-Variant voice-radar60`，需要已激活ESP-IDF环境。两种雷达版待机时上传最新观测，通话时暂停上传但继续本地采集。详情见[可选雷达固件.md](../../可选雷达固件.md)。

这些文件只有应用分区内容。本机已连接设备的应用偏移为0x10000，其他设备必须先核对分区和OTA选择；不能用它们覆盖引导程序、分区表或整片Flash。刷写前备份现有固件及配置。设备备份与串口日志仅保存在Git忽略的build目录。
