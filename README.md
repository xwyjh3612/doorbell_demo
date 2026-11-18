# ESP32 4G 语音对讲

ESP32-S3 + ML307 4G 设备通过 MQTT 交换 WebRTC 信令，与浏览器进行 Opus 16kHz 单声道语音对讲。`audio_server` 是 Spring Boot 信令桥接服务，不承载音频编解码。

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

## OTA

仅在空闲状态启动升级，升级期间禁止新呼叫。URL 与 MD5 在创建下载任务前检查。MD5 缺失或为空时保持现有升级行为；提供 32 位十六进制 MD5 时，在接收数据期间计算，下载完成后比对。校验失败不会切换启动分区，并释放 OTA 写入句柄。

## 构建与测试

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

当前自动化覆盖 8 个通话场景、8 个 OTA 场景和 9 个 Java 协议兼容用例。主机测试不验证 ML307 实际网络、音质或设备重启，需要硬件联调确认这些行为。

## 阅读入口

- `main/main.cpp`：设备初始化。
- `main/webrtc_mqtt.c`：通话控制与重拨。
- `main/mqtt_signaling.cpp`：保持现有设备协议的 MQTT 实现。
- `main/otaupgrade.cpp`：HTTP OTA、校验与资源清理。
- `audio_server/src/main/java`：WebSocket 与 MQTT 信令桥接。
- `MAIN系统功能梳理.md`、`MQTT信令简要说明.md`、`audio_server/AI_PROJECT_GUIDE.md`：详细模块说明。
