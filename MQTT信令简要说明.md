# MQTT 信令简要说明与 JSON 示例

> 说明：本文档聚焦 `main/mqtt_signaling.cpp` 当前实现的 MQTT 信令协议，方便联调、查阅和后续修改。
>
> 注意：以下内容以当前源码实现为准，若后续协议变更，请同步更新本文档。

---

# 1. 信令总体说明

当前系统的信令通道使用 **MQTT**，主要负责：

- ICE 服务器请求与下发
- WebRTC SDP 交换（offer / answer）
- ICE candidate 交换
- 呼叫控制（reject / bye / timeout）
- 自定义控制命令（customized）
- 版本查询
- OTA 升级指令

媒体数据本身不走 MQTT，而是：

- **音频媒体走 WebRTC**
- **底层 UDP 通过 4G 模组适配层实现**

也就是说：

- MQTT 负责“怎么建立连接、怎么控制连接”
- WebRTC/UDP 负责“真正传输音频”

---

# 2. Topic 规则

Topic 由 `app_config` 中的配置动态生成。

## 上行 Topic
设备 -> 服务端：

```text
<base_topic>/<device_id>/up
```

## 下行 Topic
服务端 -> 设备：

```text
<base_topic>/<device_id>/down
```

## 默认示例
如果配置为：

- `base_topic = /voice/project`
- `device_id = 123456789012`

那么：

### 上行
```text
/voice/project/123456789012/up
```

### 下行
```text
/voice/project/123456789012/down
```

---

# 3. 当前支持的消息类型

根据 `mqtt_signaling.cpp`，当前主要消息类型如下：

## 设备上行常见消息
- `ice_request`
- `offer`
- `answer`
- `candidate`
- `bye`
- `timeout`
- `version_report`

## 服务端下行常见消息
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

# 4. 各消息说明与 JSON 示例

---

## 4.1 `ice_request`

## 作用
设备启动 signaling 或网络恢复后，向服务端请求 ICE 服务器信息。

## 方向
设备 -> 服务端

## 设备发送示例
```json
{
  "type": "ice_request",
  "timestamp": 1711612345
}
```

## 说明
当前源码里只带两个字段：

- `type`
- `timestamp`

这个消息不包含 `from`。

---

## 4.2 `ice_response`

## 作用
服务端返回 ICE 服务器信息，设备收到后喂给 WebRTC。

## 方向
服务端 -> 设备

## 服务端下发示例
```json
{
  "type": "ice_response",
  "iceServers": [
    {
      "urls": [
        "turn:turn.example.com:3478"
      ],
      "username": "test_user",
      "credential": "test_pass"
    }
  ]
}
```

## 关键字段
- `iceServers`：数组
- `urls`：数组，当前代码只取第一个
- `username`
- `credential`

## 源码处理逻辑
收到后会保存到：

- `ice_url`
- `ice_user`
- `ice_psw`

然后通过 `on_ice_info()` 通知 WebRTC。

---

## 4.3 `offer`

## 作用
主叫发起 WebRTC SDP offer。

## 方向
主叫 -> 服务端 -> 被叫设备

## 上行/下行格式示例
```json
{
  "type": "offer",
  "from": "123456789012",
  "data": "v=0\r\no=- 46117317 2 IN IP4 127.0.0.1\r\n..."
}
```

## 关键字段
- `type`
- `from`
- `data`：SDP 字符串

## 源码行为
### 主叫发送时
`mqtt_signal_send_msg()` 根据 `sg->is_initiator == true` 发送为 `offer`。

### 被叫收到时
设备不会立刻完成建链，而是：

- 缓存 `pending_sdp`
- 记录 `incoming_offer_from`
- 设置 `pending_offer_waiting = true`
- 后续 candidate 也先缓存
- 通知业务层进入来电状态

这是当前“先响铃，后接听”的实现基础。

---

## 4.4 `answer`

## 作用
被叫接听后，返回 WebRTC SDP answer。

## 方向
被叫 -> 服务端 -> 主叫设备

## JSON 示例
```json
{
  "type": "answer",
  "from": "123456789012",
  "data": "v=0\r\no=- 46117317 2 IN IP4 127.0.0.1\r\n..."
}
```

## 关键字段
- `type`
- `from`
- `data`

## 源码行为
收到 `answer` 后：

- 触发 `MQTT_SIG_EVENT_REMOTE_ANSWER`
- 把 `data` 作为 SDP 交给 WebRTC signaling 回调

---

## 4.5 `candidate`

## 作用
交换 WebRTC ICE candidate。

## 方向
双向

## JSON 示例
```json
{
  "type": "candidate",
  "from": "123456789012",
  "candidate": "candidate:842163049 1 udp 1677729535 192.168.1.10 55555 typ srflx raddr 0.0.0.0 rport 0"
}
```

## 关键字段
- `type`
- `from`
- `candidate`

## 源码行为
### 普通情况下
收到后会直接交给 WebRTC。

### 如果当前是“被叫等待接听”阶段
如果 `pending_offer_waiting == true`：

- candidate 不会立刻处理
- 会先缓存到 `pending_candidates[]`
- 等用户接听后再统一回灌

当前缓存上限是 10 条。

---

## 4.6 `customized`

## 作用
承载自定义控制命令。

## 方向
一般为服务端/对端 -> 设备

## JSON 示例
```json
{
  "type": "customized",
  "data": "ACCEPT_CALL"
}
```

## 常见命令值
根据当前代码，常见有：

- `ACCEPT_CALL`
- `RING`
- `OPEN_DOOR`
- `DOOR_OPENED`
- `DENY_CALL`
- `REJECT_CALL`

## 源码行为
收到后会转成 `ESP_PEER_SIGNALING_MSG_CUSTOMIZED`，再交给 WebRTC/业务层处理。

注意：
当前“自定义命令”的最终处理并不都在 `mqtt_signaling.cpp`，还会继续流到：

- `webrtc_mqtt.c::door_bell_on_cmd()`

---

## 4.7 `bye`

## 作用
表示对端关闭会话 / 挂断。

## 方向
双向

## JSON 示例
```json
{
  "type": "bye",
  "from": "123456789012"
}
```

## 源码行为
收到后：

- 触发 `MQTT_SIG_EVENT_REMOTE_CLOSE`
- 再向 WebRTC signaling 层发送 `ESP_PEER_SIGNALING_MSG_BYE`

业务层通常会据此做挂断清理。

---

## 4.8 `reject`

## 作用
表示对端拒绝接听。

## 方向
被叫 -> 服务端 -> 主叫

## JSON 示例
```json
{
  "type": "reject",
  "from": "123456789012"
}
```

## 源码行为
收到后：

- 触发 `MQTT_SIG_EVENT_REMOTE_REJECT`
- 同时向 WebRTC signaling 层发一个 `BYE` 类型消息用于关闭会话

---

## 4.9 `timeout`

## 作用
主叫长时间未接通时，通知对端本次呼叫超时。

## 方向
设备 -> 服务端

## JSON 示例
```json
{
  "type": "timeout",
  "from": "123456789012",
  "timestamp": 1711612345
}
```

## 触发条件
当前 `webrtc_mqtt.c` 中主叫超时任务固定等待 10 秒：

- 若仍未接通
- 发送 `timeout`
- 本地清理会话状态

---

## 4.10 `version_query`

## 作用
服务端查询当前设备固件版本。

## 方向
服务端 -> 设备

## JSON 示例
```json
{
  "type": "version_query"
}
```

## 源码行为
收到后，设备会回复 `version_report`。

---

## 4.11 `version_report`

## 作用
设备上报当前固件版本。

## 方向
设备 -> 服务端

## JSON 示例
```json
{
  "type": "version_report",
  "version": "2",
  "from": "123456789012"
}
```

## 说明
当前版本号来自：

```c
FIRMWARE_VERSION
```

注意当前 `version` 字段是字符串，不是数字。

---

## 4.12 `ota`

## 作用
服务端下发 OTA 升级指令。

## 方向
服务端 -> 设备

## JSON 示例
```json
{
  "type": "ota",
  "url": "http://example.com/firmware.bin",
  "version": 3,
  "md5": "0123456789abcdef0123456789abcdef"
}
```

## 关键字段
- `url`：固件下载地址
- `version`：目标版本号
- `md5`：当前协议有该字段

## 源码行为
设备收到后：

1. 比较 `version` 和当前 `FIRMWARE_VERSION`
2. 若目标版本更高，则调用 `ota_start_upgrade(url, md5)`
3. 然后走 4G HTTP 下载流程

## 当前实现注意点
虽然协议里传了 `md5`，但当前 OTA 实现里 **md5 尚未真正做校验**。

---

# 5. 一个完整呼叫过程示例

这里给一个简化示意，方便联调时参考。

---

## 5.1 设备启动后请求 ICE

### 设备上行
```json
{
  "type": "ice_request",
  "timestamp": 1711612345
}
```

### 服务端下行
```json
{
  "type": "ice_response",
  "iceServers": [
    {
      "urls": ["turn:turn.example.com:3478"],
      "username": "user1",
      "credential": "pass1"
    }
  ]
}
```

---

## 5.2 主叫发起通话

### 主叫上行 offer
```json
{
  "type": "offer",
  "from": "device_a",
  "data": "v=0\r\n...offer sdp..."
}
```

### 后续上行 candidate
```json
{
  "type": "candidate",
  "from": "device_a",
  "candidate": "candidate:1 1 udp 123456 1.2.3.4 5678 typ host"
}
```

---

## 5.3 被叫接听后返回 answer

### 被叫上行 answer
```json
{
  "type": "answer",
  "from": "device_b",
  "data": "v=0\r\n...answer sdp..."
}
```

### 被叫上行 candidate
```json
{
  "type": "candidate",
  "from": "device_b",
  "candidate": "candidate:2 1 udp 654321 5.6.7.8 9999 typ host"
}
```

---

## 5.4 对端拒绝

```json
{
  "type": "reject",
  "from": "device_b"
}
```

---

## 5.5 对端挂断

```json
{
  "type": "bye",
  "from": "device_b"
}
```

---

## 5.6 呼叫超时

```json
{
  "type": "timeout",
  "from": "device_a",
  "timestamp": 1711612400
}
```

---

# 6. 联调时建议重点关注的字段

联调 MQTT 时，建议最关注这些字段：

- `type`
- `from`
- `data`
- `candidate`
- `iceServers`
- `url`
- `version`
- `md5`
- `timestamp`

其中最核心的是：

- `type`：决定走哪条逻辑
- `from`：对端标识
- `data`：SDP 内容
- `candidate`：ICE candidate 内容

---

# 7. 当前协议实现上的几个注意点

## 1）`ice_request` 当前不带 `from`
如果服务端需要按设备来源做更严格识别，需要结合 topic 或后续扩展字段。

## 2）`version_report.version` 当前是字符串
联调时不要按纯 number 强校验。

## 3）`candidate` 当前字段名就是 `candidate`
不是 `data`。

## 4）`offer/answer` 的 SDP 当前走 `data`
这一点要和 candidate 区分开。

## 5）`ota.md5` 当前协议里有，但设备端未真正校验
服务端设计时要知道这一点。

## 6）被叫在未接听前会缓存 `offer/candidate`
所以服务端看到消息到了，不等于设备已经立刻进入 WebRTC connected。

---

# 8. 一页速查

## 常用 type 一览

- `ice_request`：请求 ICE
- `ice_response`：下发 ICE
- `offer`：主叫 SDP
- `answer`：被叫 SDP
- `candidate`：ICE candidate
- `customized`：自定义命令
- `bye`：挂断
- `reject`：拒绝
- `timeout`：超时
- `version_query`：查版本
- `version_report`：回版本
- `ota`：下发升级

---

> 建议：如果后续服务端协议要扩展，优先保持 `type` 主字段不变，再逐步增加字段，避免直接破坏当前设备端解析逻辑。
