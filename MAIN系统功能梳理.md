# doorbell_demo_voice `main` 目录系统功能梳理

> 文档目的：帮助后续维护人员快速理解 `main` 目录当前实际生效的系统架构、模块职责、通信逻辑、升级逻辑、状态流转、关键风险点与推荐修改入口。
>
> 说明：本文档基于当前 `main` 目录及其实际编译入口梳理，重点面向**当前在跑的主线路径**，不是历史遗留/备用代码路径。

---

# 1. 系统整体定位

这是一个基于 ESP32 的语音通话设备**，当前主线方案是：

- **网络接入**：4G 模组（ML307，AT 指令控制）
- **信令层**：MQTT
- **媒体层**：WebRTC
- **音频链路**：单声道 Opus，16kHz
- **UDP/ICE/STUN**：通过自定义 `ml307_udp_socket` 适配到 4G 模组
- **控制能力**：铃声、接听、拒绝、挂断、开门(停用)等
- **远程升级**：MQTT 下发 OTA 指令，4G HTTP 下载固件并写入 OTA 分区

当前系统不是传统的 `Wi‑Fi + apprtc` 主线，而是：

**4G + MQTT signaling + WebRTC(P2P/ICE/UDP) + OTA**

---

# 2. 当前实际生效的源码主线

从 `main/CMakeLists.txt` 可知，当前真正参与编译的核心文件是：

- `main.cpp`
- `board.c`
- `media_sys.c`
- `webrtc_mqtt.c`
- `mqtt_signaling.cpp`
- `app_config.c`
- `network_4g.cpp`
- `ml307_udp_socket.cc`
- `door_bell_audio.c`
- `otaupgrade.cpp`

这意味着以下文件更像是**历史版本 / 对照版本 / 备用路径**：

- `webrtc.c`
- `main.cpp.wifi`

后续维护时，**优先改当前编译主线，不要误改历史文件**。

---

# 3. 系统总体架构图

```text
[用户按键 / 控制台 / 上层接口]
              |
              v
      +-------------------+
      |   webrtc_mqtt.c   |
      | 通话业务状态机     |
      +-------------------+
          |          |
          |          +-----------------------------+
          |                                        |
          v                                        v
+---------------------+                 +----------------------+
| mqtt_signaling.cpp  |                 |     media_sys.c      |
| MQTT信令/SDP/ICE     |                 | 音频采集/播放/提示音 |
+---------------------+                 +----------------------+
          |
          v
+---------------------+
|   network_4g.cpp    |
| 4G联网/MQTT客户端    |
+---------------------+
          |
          +------------------+
          |                  |
          v                  v
+---------------------+   +----------------------+
| ml307_udp_socket.cc |   |   otaupgrade.cpp     |
| UDP/ICE适配到ML307   |   | OTA下载/写分区/重启   |
+---------------------+   +----------------------+
```

---

# 4. 各核心文件职责说明

## 4.1 `main/main.cpp`

## 作用
系统总入口，负责：

- 基础初始化
- 板级初始化
- 配置初始化
- 4G 模组初始化
- MQTT 初始化触发
- 媒体系统初始化
- 控制台初始化
- 启动 WebRTC
- 周期性查询 WebRTC 状态

## 关键函数

### `DoorbellApp::app_main()`
主流程大致如下：

1. 设置日志级别
2. `media_lib_add_default_adapter()`
3. 设置线程调度器
4. `init_board()`
5. 打印当前固件版本 `FIRMWARE_VERSION`
6. `app_config_init()` 读取 NVS 配置
7. `new_4g()` 初始化 4G 和 MQTT
8. `media_sys_buildup()` 初始化音频系统
9. `init_console()` 初始化串口控制台
10. 异步启动 WebRTC：`run_async_start()`
11. 进入循环，每 2 秒执行一次 `query_webrtc()`

### `new_4g()`
主要做：

- `Network4g::init()`：初始化 ML307 模组
- 测试 UDP socket 是否可用
- 打印模组信息（IMEI、ICCID、信号值）
- `Network4g::initMqtt()`：创建并连接 MQTT

### `run_async_start()`
生成 `room_url`，然后调用：

- `start_webrtc(room_url)`

虽然这里看起来像传统 URL signaling，但在当前主线中，`webrtc_mqtt.c` 使用的是 `esp_signaling_get_mqtt_impl()`，所以**真正信令已经切到 MQTT**。

---

## 4.2 `main/common.h`

## 作用
对外暴露主要业务接口，是系统上层最重要的公共头之一。

## 关键接口

- `int start_webrtc(char *url);`
- `void query_webrtc(void);`
- `int stop_webrtc(void);`
- `void send_cmd(const char *cmd);`

语音通话接口：

- `int voice_call_offer(const char* target_id);`
- `int voice_call_answer(void);`
- `int voice_call_reject(void);`
- `int voice_call_close(void);`
- `const char* voice_call_get_state_name(void);`
- `const char* voice_call_get_peer_id(void);`

后续如果有 App 层 / UI 层 / 其他模块要驱动语音通话业务，通常会从这里进入。

---

## 4.3 `main/webrtc_mqtt.h`

## 作用
定义通话状态枚举及状态查询接口。

## 当前状态枚举

- `CALL_STATE_IDLE`：空闲
- `CALL_STATE_OUTGOING`：呼出中
- `CALL_STATE_OUTGOING_CONNECTING`：主叫已进入连接中
- `CALL_STATE_INCOMING`：来电等待接听
- `CALL_STATE_INCOMING_CONNECTING`：被叫已接听，连接中
- `CALL_STATE_CONNECTED`：通话中
- `CALL_STATE_RECONNECTING`：预留的重连状态

这个状态定义是后续所有业务判断的基础。

---

## 4.4 `main/webrtc_mqtt.c`

## 作用
这是当前系统的**核心业务状态机**，负责：

- 通话状态维护
- 主叫 / 被叫流程控制
- 超时控制
- 自动重拨控制
- 响铃 / 接听 / 拒绝 / 挂断
- WebRTC 事件响应
- MQTT signaling 事件转业务状态
- 呼叫按键监控

## 核心数据结构 `call_ctx_t`

当前上下文字段包括：

- `state`：当前通话状态
- `is_initiator`：是否主叫
- `hangup_by_self`：是否本地主动挂断
- `reconnect_eligible`：当前是否允许自动重拨
- `has_pending_offer`：是否有待处理远端 offer
- `was_connected_once`：本轮是否真正接通过
- `reconnect_task_running`：是否已有重拨任务在跑
- `reconnect_attempts`：已自动重拨次数
- `peer_id[32]`：当前对端 ID
- `last_remote_id[32]`：最近一次可用于重拨的对端 ID

## 核心入口函数

- `start_webrtc(char *url)`
- `stop_webrtc(void)`
- `query_webrtc(void)`
- `send_cmd(const char *cmd)`
- `voice_call_offer()`
- `voice_call_answer()`
- `voice_call_reject()`
- `voice_call_close()`

## 内部关键函数

- `on_mqtt_signaling_event()`：接收 MQTT signaling 层事件
- `door_bell_on_cmd()`：接收 WebRTC 自定义命令
- `webrtc_event_handler()`：接收 WebRTC 连接事件
- `call_timeout_task()`：呼叫超时任务
- `auto_reconnect_task()`：自动重拨任务
- `call_ctx_change_state()`：状态切换
- `call_ctx_reset_idle()`：重置为空闲状态

## 当前业务规则总结

### 主叫流程
- 从 `IDLE` 才允许发起呼叫
- 呼出后状态进入 `OUTGOING`
- 对端答复后进入 `OUTGOING_CONNECTING`
- WebRTC connected 后进入 `CONNECTED`

### 被叫流程
- 收到远端 `offer` / `ring` 后进入 `INCOMING`
- 本地接听后进入 `INCOMING_CONNECTING`
- WebRTC connected 后进入 `CONNECTED`

### 超时
- 主叫阶段有固定 10 秒超时任务
- 超时后向对端发 `timeout`
- 然后回到 `IDLE`

### 自动重拨
当前已经按保守方案加入：

- 最大 3 次
- 固定延迟 1500ms
- **只在已接通过一次后异常断开时触发**
- **只允许主叫触发**
- **本地主动挂断不重拨**
- 未接通前失败不重拨

## 后续维护建议
凡是涉及：

- 呼叫状态机
- 呼叫行为规则
- 接听/挂断/拒绝
- 自动重拨策略
- 通话超时策略

都应该优先看和改这个文件。

---

## 4.5 `main/mqtt_signaling.h`

## 作用
定义 MQTT 信令层接口和事件。

## 关键事件

- `MQTT_SIG_EVENT_REMOTE_RING`
- `MQTT_SIG_EVENT_REMOTE_OFFER`
- `MQTT_SIG_EVENT_REMOTE_ANSWER`
- `MQTT_SIG_EVENT_REMOTE_REJECT`
- `MQTT_SIG_EVENT_REMOTE_CLOSE`
- `MQTT_SIG_EVENT_REMOTE_TIMEOUT`

## 关键接口

- `esp_signaling_get_mqtt_impl()`
- `mqtt_sig_set_device_id()`
- `mqtt_sig_set_webrtc_handle()`
- `mqtt_sig_set_event_handler()`
- `mqtt_sig_send_ring()`
- `mqtt_sig_send_timeout()`
- `mqtt_sig_trigger_offer()`
- `mqtt_sig_answer_call()`
- `mqtt_sig_reject_call()`
- `mqtt_sig_close_call()`
- `mqtt_sig_restart()`

---

## 4.6 `main/mqtt_signaling.cpp`

## 作用
这是当前系统的**核心信令处理文件**，负责：

- MQTT 连接后的 topic 订阅
- MQTT 上下行 JSON 消息编码 / 解码
- ICE 信息请求与下发
- SDP (`offer/answer`) 交换
- ICE candidate 交换
- `bye/reject/timeout` 等控制消息
- OTA / version_query 消息入口

## 核心结构 `mqtt_sig_t`

关键字段：

- `device_id`
- `peer_id`
- `ice_url`
- `ice_user`
- `ice_psw`
- `signaling_ready`
- `is_initiator`
- `ice_reload_started`
- `cfg`：WebRTC signaling 回调配置
- `pending_sdp`
- `incoming_offer_from`
- `pending_offer_waiting`
- `pending_candidates[10]`
- `pending_candidate_count`

## topic 组织方式
由 `app_config` 动态生成：

- 上行：`<base_topic>/<device_id>/up`
- 下行：`<base_topic>/<device_id>/down`

例如默认可能类似：

- `/voice/project/<device_id>/up`
- `/voice/project/<device_id>/down`

## 核心流程函数

### `mqtt_signal_start()`
作用：

- 初始化 `mqtt_sig_t`
- 设置 MQTT 回调
- 若已连接，则立即订阅 down topic 并发送 `ice_request`
- 通知 signaling ready

### `mqtt_signal_send_msg()`
把 WebRTC signaling 层产生的数据发成 MQTT JSON：

- SDP -> `offer` / `answer`
- candidate -> `candidate`
- BYE -> `bye`

### `mqtt_message_handler()`
解析下行 JSON 消息，是整个协议逻辑入口之一。

当前主要识别消息类型：

- `ice_response`
- `offer`
- `answer`
- `candidate`
- `customized`
- `bye`
- `reject`
- `ota`
- `version_query`

## 最关键的几个协议行为

### 1）ICE 请求 / 响应
设备端上行发：

- `ice_request`

服务端返回：

- `ice_response`

然后把 `urls / username / credential` 喂给 WebRTC。

### 2）主叫 offer / 被叫 answer
主叫产生 SDP 后通过 MQTT 发 `offer`；
被叫接收后先缓存，不立即交给 WebRTC 完整连接。

### 3）被叫缓存机制
收到远端 `offer` 时：

- 缓存 `pending_sdp`
- 缓存 `incoming_offer_from`
- 后续到来的 candidate 也缓存到 `pending_candidates[]`

等用户真正执行 `answer` 时，`mqtt_sig_answer_call()` 才会：

- 恢复 ICE 信息
- 打开 peer connection
- 回灌缓存的 SDP
- 回灌缓存的 candidates

这就是“先响铃、用户接听后再正式建链”的关键机制。

### 4）关闭 / 拒绝 / 超时
这部分通过 MQTT JSON 控制：

- `bye`
- `reject`
- `timeout`

## 后续维护建议
凡是涉及：

- MQTT 协议字段变化
- SDP/ICE 流程变化
- topic 变化
- 服务器交互方式变化
- OTA / version 消息协议变化

都应该优先看这个文件。

---

## 4.7 `main/network_4g.h / main/network_4g.cpp`

## 作用
4G 模组及 MQTT 客户端管理中心，负责：

- ML307 模组初始化
- 网络就绪检测
- MQTT 客户端创建
- 网络恢复后的 MQTT 重建
- 域名解析

## 关键静态对象

- `std::unique_ptr<AtModem> modem`
- `std::unique_ptr<Mqtt> mqtt`
- `bool initialized`

## 关键函数

### `Network4g::init()`
主要流程：

1. `AtModem::Detect(...)`
2. 注册 `OnNetworkStateChanged(...)`
3. 等待网络 ready
4. 打印模组信息

### `Network4g::initMqtt()`
主要流程：

- 通过 `modem->CreateMqtt(0)` 创建 MQTT 客户端
- 从 `app_config_get()` 中读取：
  - `mqtt_host`
  - `mqtt_port`
  - `mqtt_user`
  - `mqtt_password`
- 调用 `Connect(...)`

### `OnNetworkStateChanged(...)`
当前网络恢复机制的核心。

当网络恢复且系统已初始化后，会：

1. 创建一个延迟任务
2. 延迟 2 秒
3. `initMqtt()`
4. `mqtt_sig_restart()`

也就是：

**断网恢复后，先重建 MQTT，再恢复 signaling 订阅与 ICE 请求。**

### `resolveDomain()`
通过 ML307 AT 域名解析，返回 IPv4 地址字符串。

## 后续维护建议
凡是涉及：

- 4G 网络恢复策略
- MQTT 客户端生命周期
- DNS 解析
- 模组初始化顺序

都应该优先看这个文件。

---

## 4.8 `main/ml307_udp_socket.h / main/ml307_udp_socket.cc`

## 作用
把 WebRTC 期望的 UDP socket 接口，适配到底层 ML307 模组的 UDP 能力上。

这是整个 4G WebRTC 跑通的关键适配层。

## 当前实现方式
内部通过 `UdpManager` 管理最多 `MAX_CONN = 3` 个连接。

每个连接 `UdpConnection` 主要保存：

- `udp`
- `last_packet`
- `has_packet`
- `remote_ip`
- `remote_port`
- `last_used`

## 对外提供的关键接口

- `udp_socket_open()`
- `udp_socket_sendto()`
- `udp_socket_recvfrom_nowait()`
- `udp_socket_close()`
- `udp_get_local_address()`
- `ports_resolve_addr()`
- `ports_get_host_addr()`

## 主要作用
- 给 WebRTC/peer 层提供一个“像普通 UDP socket 一样”的接口
- 实际内部由 4G 模组完成 UDP 收发
- ICE/STUN/WebRTC candidate 流量也都依赖这里

## 维护重点
如果后面出现：

- 丢包
- candidate 不稳定
- 通话建立时好时坏
- 弱网下异常断流

这个文件一定要重点排查。

---

## 4.9 `main/app_config.h / main/app_config.c`

## 作用
系统配置中心，负责：

- 默认配置定义
- 从 NVS 读取配置
- 更新配置并写回 NVS
- 自动生成 device_id

## 配置结构 `app_config_t`

字段包括：

- `mqtt_host`
- `mqtt_port`
- `mqtt_user`
- `mqtt_password`
- `device_id`
- `base_topic`
- `ice_refresh_interval`
- `call_timeout`

## 默认值
当前默认值包括：

- `mqtt_host = "visit-repair.2811.top"`
- `mqtt_port = 1883`
- `mqtt_user = "esp32_client"`
- `mqtt_password = ""`
- `device_id = "esp32_001"`
- `base_topic = "/voice/project"`
- `ice_refresh_interval = 1800`
- `call_timeout = 120`

## device_id 生成逻辑
如果 NVS 中没有 `device_id`：

- 读取 MAC
- 转成字符串
- 保存到 NVS

## 当前实际生效情况
### 明显生效的配置
- MQTT 地址与端口
- MQTT 用户名密码
- `device_id`
- `base_topic`

### 定义了但未完全打通的配置
- `ice_refresh_interval`
- `call_timeout`

例如当前呼叫超时在 `webrtc_mqtt.c` 里仍然固定写死为 10 秒，没有完全走配置项。

---

## 4.10 `main/otaupgrade.h / main/otaupgrade.cpp`

## 作用
负责 OTA 升级下载、写入 OTA 分区、切换启动分区并重启。

## 版本号定义
在 `otaupgrade.h` 中：

```c
#define FIRMWARE_VERSION 2
```

## 关键接口

- `ota_start_upgrade(const char* url, const char* md5)`

## 核心流程
1. 检查 4G 模组和网络状态
2. 创建 OTA 上下文
3. 通过 AT 指令创建 HTTP 会话
4. 发起 HTTP GET 下载固件
5. 通过 URC 回调接收 header 和 content
6. content 做 HEX 解码
7. 调用 `esp_ota_write()` 写 OTA 分区
8. 下载完成后校验大小
9. `esp_ota_end()`
10. `esp_ota_set_boot_partition()`
11. `esp_restart()`

## 重要事实
虽然 OTA 命令会�� `md5`，但当前实现中 **`md5` 参数没有真正使用**。

这意味着目前 OTA 完整性主要依赖：

- HTTP 下载成功
- Content-Length 匹配
- `esp_ota_end()` 的镜像校验

而不是业务层的 MD5 比对。

---

## 4.11 `main/board.c`

## 作用
音频板级初始化。

主要做：

- 设置 codec board type
- 初始化 codec 输入输出模式

与实际硬件相关性很强。

---

## 4.12 `main/media_sys.c`

## 作用
音频系统总装，负责：

- 音频采集
- 音频播放
- 提示音播放器
- 为 WebRTC 提供媒体 provider

## 核心函数

- `media_sys_buildup()`
- `media_sys_get_provider()`
- `play_music()`
- `stop_music()`
- `test_capture_to_player()`

## 作用说明
- WebRTC 音频链路靠这里提供输入输出
- 呼叫提示音也靠这里播放

---

## 4.13 `main/door_bell_audio.c`

## 作用
呼叫提示音的简单封装。

当前主要提示音：

- 响铃音
- 开门音
- 加入成功音

这是业务层提示反馈的重要一层。

---

# 5. 通信逻辑详解

这一部分是后续维护最关键的内容之一。

---

## 5.1 通信分层概览

当前系统不是单通道通信，而是多层组合：

### 网络承载层
- 4G 模组（ML307）

### 控制/信令层
- MQTT

### 媒体层
- WebRTC 音频

### UDP 适配层
- `ml307_udp_socket`

### 控制命令层
- MQTT JSON + WebRTC customized signaling 双通路混合

---

## 5.2 4G 网络逻辑

当前主线以 `network_4g.cpp` 为准。

### 初始化流程
- 检测 AT 模组
- 等待网络 ready
- 创建设备 MQTT 客户端

### 网络恢复逻辑
当 4G 短暂断开又恢复时：

- 重新 `initMqtt()`
- 再调用 `mqtt_sig_restart()`

这个逻辑说明：

**断网恢复主要是先恢复 MQTT 控制面，而不是完全无缝恢复 WebRTC 媒体面。**

---

## 5.3 MQTT 通信逻辑

## topic 组织
主题基于配置动态生成：

- 上行：`<base_topic>/<device_id>/up`
- 下行：`<base_topic>/<device_id>/down`

### MQTT 初始化
MQTT 由 4G 模组创建，成功连接后：

- 订阅 down topic
- 发送 `ice_request`
- signaling 进入 ready

### MQTT 上行消息类型
当前系统会发送的典型消息包括：

- `ice_request`
- `offer`
- `answer`
- `candidate`
- `bye`
- `reject`
- `timeout`
- `version_report`

### MQTT 下行消息类型
当前系统处理的典型消息包括：

- `ice_response`
- `offer`
- `answer`
- `candidate`
- `customized`
- `bye`
- `reject`
- `ota`
- `version_query`

---

## 5.4 WebRTC 通信逻辑

## 初始化方式
在 `start_webrtc()` 中：

- 使用 `esp_peer_get_default_impl()` 作为 peer 实现
- 使用 `esp_signaling_get_mqtt_impl()` 作为 signaling 实现
- 设置音频方向为 `SEND_RECV`
- 视频关闭
- `no_auto_reconnect = true`

### 一个关键点
WebRTC 实例创建后，初始是：

- `esp_webrtc_enable_peer_connection(webrtc, false)`

也就是：

**WebRTC 先被打开，但 peer connection 默认禁用，等业务流程到了正确阶段才启用。**

---

## 5.5 ICE / SDP / Candidate 逻辑

这是 WebRTC 建链的核心。

### ICE 获取
1. MQTT 上行发 `ice_request`
2. 服务端下发 `ice_response`
3. 设备解析出：
   - `urls`
   - `username`
   - `credential`
4. 回调给 WebRTC

### SDP 交换
- 主叫侧产生 `offer`，经 MQTT 发给服务端/对端
- 被叫侧收到 `offer`
- 被叫接听后产生 `answer`
- answer 经 MQTT 发回主叫

### Candidate 交换
- 本地 candidate -> MQTT 上行 `candidate`
- 远端 candidate -> MQTT 下行 `candidate`

### 被叫缓存设计
被叫收到 `offer` 时并不立即建链，而是：

- 缓存 `pending_sdp`
- 缓存 `pending_candidates[]`
- 等用户接听
- 接听后统一回灌给 WebRTC

这正是当前“铃声先响，用户确认后再接通”的业务基础。

---

## 5.6 控制命令逻辑

当前控制命令来自两条路径。

## 路径 A：WebRTC customized signaling
在 `door_bell_on_cmd()` 中处理，典型命令包括：

- `RING`
- `OPEN_DOOR`
- `DOOR_OPENED`
- `ACCEPT_CALL`
- `DENY_CALL`
- `REJECT_CALL`

用途偏向：

- 呼叫提示
- 接听反馈
- 开门反馈
- 对端拒绝反馈

## 路径 B：MQTT JSON 消息
在 `mqtt_message_handler()` 中处理：

- `offer`
- `answer`
- `candidate`
- `bye`
- `reject`
- `ota`
- `version_query`

用途偏向：

- 真正信令交换
- OTA 指令
- 版本查询
- 会话控制

### 结论
当前控制面是**混合双通道设计**，后续改协议时要注意：

- 哪些指令走 MQTT JSON
- 哪些指令走 WebRTC customized command

否则容易改一半出问题。

---

# 6. 通话业务逻辑

---

## 6.1 主叫流程

可能的触发源：

- GPIO 按键
- 控制台命令
- 上层直接调用 `voice_call_offer(target_id)`

## 典型步骤
1. 本地触发 `ring`
2. 当前状态必须是 `IDLE`
3. 设置为主叫：`is_initiator = true`
4. 状态进入 `OUTGOING`
5. 播放响铃提示音
6. 经 MQTT signaling 发起呼叫
7. 启动呼叫超时任务
8. 对端回复 `answer`
9. 状态进入 `OUTGOING_CONNECTING`
10. WebRTC connected
11. 状态进入 `CONNECTED`

---

## 6.2 被叫流程

## 典型步骤
1. MQTT 下行收到 `offer`
2. signaling 层缓存远端 SDP 和 candidates
3. 业务层状态进入 `INCOMING`
4. 播放响铃音
5. 用户选择接听
6. `mqtt_sig_answer_call()` 回灌缓存 SDP/candidate
7. 状态进入 `INCOMING_CONNECTING`
8. WebRTC connected
9. 状态进入 `CONNECTED`

---

## 6.3 拒绝 / 挂断 / 超时

### 拒绝
- 被叫在 `INCOMING` 或 `INCOMING_CONNECTING` 阶段可拒绝
- 发送 `reject`
- 清理本地状态并回到 `IDLE`

### 挂断
- 本地主动 close 时：
  - 标记 `hangup_by_self = true`
  - 发送 `close/bye`
  - 关闭 WebRTC
  - 清理状态

### 超时
- 当前主叫超时固定 10 秒
- 超时后发送 `timeout`
- 回到 `IDLE`

---

## 6.4 自动重拨逻辑

当前已经加入保守自动重拨策略：

### 触发条件
必须同时满足：

- 当前设备是主叫
- 不是本地主动挂断
- 本轮通话曾真正接通过一次
- `last_remote_id` 有效
- 已重拨次数小于 3
- 当前没有已有重拨任务在跑

### 触发时机
- 仅在 `CONNECTED` 之后异常断开时触发

### 不触发场景
- 呼出超时
- 未接通前 `CONNECT_FAILED`
- 对端明确拒绝
- 本地主动 `close`
- 本地 `reject`
- `stop_webrtc()`

### 执行方式
- 延迟 1500 ms
- 重新发起一轮新呼叫
- 最多 3 次

这个设计的核心思想是：

**不尝试恢复旧 WebRTC 会话，而是业务层重新发起一轮新呼叫。**

---

# 7. 升级逻辑详解

---

## 7.1 版本号机制

当前版本号由宏定义控制：

```c
#define FIRMWARE_VERSION 2
```

启动时会打印当前版本。

---

## 7.2 版本查询逻辑

当 MQTT 下行收到：

- `version_query`

设备会回：

- `version_report`

报告内容中包含当前版本号。

这通常用于服务端先判断设备版本，再决定是否推送 OTA。

---

## 7.3 OTA 触发逻辑

服务端下发类似 JSON：

```json
{
  "type": "ota",
  "url": "http://.../firmware.bin",
  "version": 3,
  "md5": "xxxx"
}
```

设备处理逻辑：

1. 解析 `url`
2. 解析 `version`
3. 解析 `md5`
4. 若目标版本小于等于当前版本，则跳过
5. 否则执行 `ota_start_upgrade(url, md5)`

---

## 7.4 OTA 执行逻辑

OTA 真正下载不走 MQTT，而是：

- 通过 4G 模组发 HTTP GET
- 固件数据经 AT URC 流回来
- HEX 解码后写入 OTA 分区

### 核心阶段
- 创建 HTTP 会话
- 配置 fragment 和 timeout
- 发送 GET 请求
- 解析 header
- 获取 `Content-Length`
- 持续接收 content
- `esp_ota_write()` 写入
- 写完后 `esp_ota_end()`
- 设置 boot partition
- 重启设备

---

## 7.5 OTA 当前限制和风险

### 已有保护
- 防止重复并发 OTA
- 要求 4G 网络 ready
- 要求下载大小匹配
- 要求 OTA 分区写入成功

### 当前缺失
#### 1）没有真正使用 md5
虽然协议里传了 `md5`，但当前实现没有校验。

#### 2）没有严格限制“通话中禁止升级”
代码注释有“空闲状态才允许升级”的语义，但**当前 OTA 入口并没有真正判断当前是否在通话中**。

#### 3）没有升级进度上报
当前主要是本地日志，没有标准的 OTA 进度回传机制。

#### 4）没有业务级回滚策略
当前依赖 ESP-IDF OTA 机制本身，不具备完整业务层失败回退流程。

---

# 8. 配置与持久化逻辑

---

## 8.1 持久化介质
- NVS
- namespace：`app_config`

## 8.2 当前主要持久化项目
- `mqtt_host`
- `mqtt_port`
- `mqtt_user`
- `mqtt_password`
- `device_id`
- `base_topic`
- `ice_interval`
- `call_timeout`

## 8.3 device_id 逻辑
第一次运行时如果没配：

- 通过 MAC 生成 ID
- 写入 NVS
- 后续保持稳定

这意味着设备 MQTT topic 和设备身份会比较稳定。

---

# 9. 线程 / 任务 / 事件流梳理

---

## 9.1 主循环线程
由 `app_main()` 驱动，负责：

- 初始化
- 启动各模块
- 周期性 `query_webrtc()`

---

## 9.2 媒体相关线程
由 `main.cpp` 中调度器统一配置优先级和栈大小，涉及：

- `buffer_in`
- `venc_0`
- `aenc_0`
- `Adec / adec_0`
- `AUD_SRC`
- `pc_task`
- `start`
- `leave`

其中与当前最密切的通常是：

- `AUD_SRC`
- `aenc_0`
- `adec_0`
- `pc_task`

---

## 9.3 FreeRTOS 显式任务
当前比较重要的任务包括：

- `auto_reconnect`：自动重拨
- `call_timeout`：呼叫超时
- `mqtt_restart`：网络恢复后重建 MQTT/signaling
- `mqtt_msg_async`：异步处理 MQTT 消息
- `ota_task`：OTA 下载任务
- `music_player`：提示音播放
- `key_monitor_thread`：按键监控

---

## 9.4 主要事件源

### 4G 网络事件
- `OnNetworkStateChanged`

### MQTT 连接事件
- `OnConnected`
- `OnDisconnected`

### MQTT 消息事件
- `OnMessage -> mqtt_message_handler`

### WebRTC 事件
- `ESP_WEBRTC_EVENT_CONNECTING`
- `ESP_WEBRTC_EVENT_CONNECTED`
- `ESP_WEBRTC_EVENT_DISCONNECTED`
- `ESP_WEBRTC_EVENT_CONNECT_FAILED`

### OTA 事件
- HTTP 创建成功
- Header 收到
- 下载完成
- 下载错误

---

# 10. 典型时序梳理

---

## 10.1 启动时序

1. `app_main()`
2. `init_board()`
3. 打印版本号
4. `app_config_init()`
5. `new_4g()`
6. `Network4g::init()`
7. `Network4g::initMqtt()`
8. `media_sys_buildup()`
9. `init_console()`
10. 启动 `run_async_start()`
11. `start_webrtc()`
12. WebRTC 打开，注册 signaling / media / event handler
13. MQTT 连接后订阅下行 topic
14. 发送 `ice_request`
15. 主循环持续 `query_webrtc()`

---

## 10.2 主叫时序

1. 本地发起 `ring`
2. 状态从 `IDLE -> OUTGOING`
3. MQTT signaling 发起呼叫
4. 启动超时任务
5. 收到远端 `answer`
6. `OUTGOING -> OUTGOING_CONNECTING`
7. WebRTC 建链
8. `CONNECTED`

---

## 10.3 被叫时序

1. MQTT 下行 `offer`
2. signaling 缓存 SDP/candidate
3. 状态从 `IDLE -> INCOMING`
4. 本地响铃
5. 用户接听
6. 回灌缓存的 SDP/candidate
7. `INCOMING -> INCOMING_CONNECTING`
8. WebRTC connected
9. `CONNECTED`

---

## 10.4 断网恢复时序

1. 4G 网络断开
2. MQTT 失联
3. 网络恢复
4. `mqtt_restart` 任务启动
5. 重新 `initMqtt()`
6. `mqtt_sig_restart()`
7. 重新订阅 down topic
8. 重新请求 ICE 信息

注意：这更偏“恢复控制面”，不等于一定能无缝恢复当前媒体会话。

---

## 10.5 OTA 时序

1. 收到 MQTT `ota`
2. 解析 URL/版本号/MD5
3. 版本高于当前版本才继续
4. 启动 `ota_task`
5. 通过 4G HTTP 下载固件
6. 写 OTA 分区
7. 设置启动分区
8. 重启设备

---

# 11. 维护时最重要的风险点

---

## 风险点 1：新旧路径并存，容易看错文件

当前项目里同时存在：

- `webrtc.c`
- `webrtc_mqtt.c`
- `main.cpp.wifi`
- `main.cpp`

但**当前真正编译的是 `webrtc_mqtt.c + main.cpp`**。

后续改代码时，务必先确认修改的是当前编译入口。

---

## 风险点 2：业务状态机和 signaling 状态分散在两个文件

状态并不是只在一个地方维护：

- `webrtc_mqtt.c` 管业务状态
- `mqtt_signaling.cpp` 管 signaling 层缓存和阶段

一边改状态，另一边没同步，容易出问题。

特别是：

- `pending_sdp`
- `pending_candidates`
- `is_initiator`
- `peer_id`

这些概念跨层存在。

---

## 风险点 3：自动重拨 / 超时 / close / remote_close 之间有竞态

当前有多个并发来源同时改通话状态：

- 用户主动 close
- 超时任务
- WebRTC disconnected
- MQTT remote close
- 自动重拨任务

这些字段很多都没有锁保护，维护时必须尽量采用“最小侵入、尽量保守”的修改方式。

---

## 风险点 4：OTA 约束不完整

虽然语义上希望“空闲时才允许升级”，但目前并未严格执行。

如果后续要增强 OTA 稳定性，建议优先补：

- 通话状态检查
- 4G 信号强度检查
- md5/hash 校验
- 升级进度上报

---

## 风险点 5：UDP 适配层比较轻量，可能影响稳定性

`ml307_udp_socket.cc` 当前每个连接主要保留“最后一个包”，不是完整收包队列。

这对于 WebRTC/ICE/STUN 这种高频 UDP 业务来说，是潜在稳定性风险点。

如果出现以下问题，优先检查这里：

- 连接偶发失败
- candidate 丢失
- 断续音
- 弱网表现差

---

## 风险点 6：配置项定义和实际行为不完全一致

例如：

- `call_timeout` 配置已定义
- 但当前呼叫超时仍固定写死 10 秒

维护时不要只改 `app_config`，还要检查调用链是否真的用了该配置。

---

## 风险点 7：网络恢复只重建 MQTT，不一定完整恢复通话

当前断网恢复主要做：

- 重新连 MQTT
- 重建 signaling
- 重新请求 ICE

但未必完全重建旧 WebRTC 会话。

因此：

- 断网恢复
- 自动重拨
- WebRTC disconnected

这三块逻辑后续若要增强，需要统一设计，不能零散补丁式改。

---

# 12. 后续修改代码时的推荐入口

---

## 12.1 修改“呼叫规则 / 状态机 / 自动重拨”
优先看：

- `webrtc_mqtt.c`

重点函数：

- `send_cmd()`
- `on_mqtt_signaling_event()`
- `webrtc_event_handler()`
- `call_timeout_task()`
- `auto_reconnect_task()`

---

## 12.2 修改“MQTT 协议 / topic / SDP/ICE 交互”
优先看：

- `mqtt_signaling.cpp`
- `app_config.c`

重点函数：

- `mqtt_signal_start()`
- `mqtt_signal_send_msg()`
- `mqtt_message_handler()`
- `get_up_topic()`
- `get_down_topic()`

---

## 12.3 修改“4G 模组联网 / MQTT 生命周期 / 网络恢复”
优先看：

- `network_4g.cpp`

重点函数：

- `init()`
- `initMqtt()`
- `resolveDomain()`
- `OnNetworkStateChanged(...)`

---

## 12.4 修改“UDP / ICE / 弱网稳定性”
优先看：

- `ml307_udp_socket.cc`

重点函数：

- `udp_socket_open()`
- `udp_socket_sendto()`
- `udp_socket_recvfrom_nowait()`
- `ports_resolve_addr()`

---

## 12.5 修改“OTA 升级策略”
优先看：

- `mqtt_signaling.cpp` 中 `ota` 分支
- `otaupgrade.cpp`

重点函数：

- `mqtt_message_handler()` 中 `ota`
- `ota_start_upgrade()`
- `ota_task()`
- `http_urc_callback()`

---

## 12.6 修改“配置项 / 持久化”
优先看：

- `app_config.c`
- `app_config.h`

重点函数：

- `app_config_init()`
- `app_config_set_*()`
- `app_config_reset()`

---

# 13. 建议优先补强的几个方向

如果后续要继续演进系统，建议按下面优先级考虑：

## 第一优先级：稳定性
- 梳理 `webrtc_mqtt.c` 与 `mqtt_signaling.cpp` 的状态边界
- 收敛 close/reject/timeout/disconnect 的重复路径
- 强化 UDP 适配层收包能力

## 第二优先级：升级安全
- OTA 前检查当前通话状态必须 `IDLE`
- 使用 `md5` 或更强 hash 做完整性校验
- 增加 OTA 进度与结果上报

## 第三优先级：配置打通
- 让 `call_timeout` 真正接入业务超时逻辑
- 让 `ice_refresh_interval` 真正接入 ICE 刷新逻辑

## 第四优先级：可维护性
- 把历史文件和当前主线做更明确区分
- 为 MQTT 协议和状态机补一份单独协议文档

---

# 14. 一页结论

如果只记住最核心的几点，可以记下面这些：

1. 当前真正运行主线是：**4G + MQTT signaling + WebRTC + OTA**。
2. **业务状态机在 `webrtc_mqtt.c`，信令协议在 `mqtt_signaling.cpp`。**
3. **4G 模组不仅负责联网，还实际承载了 MQTT、UDP、HTTP。**
4. **被叫流程采用“先缓存 offer/candidate，接听后再灌入 WebRTC”的设计。**
5. **OTA 是 MQTT 触发、4G HTTP 下载，但目前还没真正用 `md5` 校验。**
6. **断网恢复目前更偏重建 MQTT/signaling，不等于完整恢复原通话。**
7. **后续最容易出问题的地方是：状态机竞态、UDP 适配层、OTA 约束不足。**

---

# 15. 文档使用建议

后续查阅时可按目的快速定位：

- 想看呼叫流程：看第 6 章
- 想看通信链路：看第 5 章
- 想看 OTA：看第 7 章
- 想看配置/NVS：看第 8 章
- 想看线程任务：看第 9 章
- 想找后续改代码入口：看第 12 章
- 想先避坑：看第 11 章

---

> 维护建议：后续每次做较大改动时，同步更新这份文档，至少更新：模块职责、时序、风险点、修改入口 四部分，这样后期接手成本会低很多。
