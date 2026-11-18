# AI 项目说明文档

> 文档位置：项目根目录  
> 适用对象：后续接手该项目的 AI / 开发者  
> 项目目录：`audio_server`

---

## 1. 项目概述

这是一个基于 **Spring Boot + WebSocket + MQTT** 的 **WebRTC 语音通话信令服务端**，主要用于在 **Web 页面** 与 **ESP32+4G 设备** 之间进行 **WebRTC 信令转发**，并提供一套简单的前端测试页面用于联调。

### 项目背景
- ESP32 设备端基于门铃项目改造而来
- 当前已演化为通用的 **WebRTC 语音通话方案**
- 设备通过 4G 模组（ML307）接入网络
- 适用于各类需要远程语音对讲的场景

### 核心定位
项目的核心职责不是直接处理音视频编解码，而是充当一个 **信令桥接层（signaling bridge）**：

- Web 端通过 **WebSocket** 连接本服务；
- ESP32+4G 设备通过 **MQTT** 与本服务通信；
- 本服务负责在两端之间转发 `offer / answer / candidate / bye / reject / ota / version_query` 等信令消息；
- 同时提供：
  - ICE 服务器配置下发
  - 设备版本上报转发
  - OTA 升级命令下发
  - 信令日志持久化
  - WebRTC 测试页面

可以把它理解为：

**WebSocket（浏览器） ⇄ Spring Boot 服务 ⇄ MQTT ⇄ ESP32+4G 设备**

---

## 2. 技术栈

### 后端
- Java 8
- Spring Boot 2.2.6.RELEASE
- Spring Web
- Spring WebSocket
- Spring Integration MQTT
- Eclipse Paho MQTT
- Lombok
- FastJSON
- Kurento Client（已引入依赖，但当前主要逻辑仍以信令转发为主）

### 前端
- 原生 HTML / CSS / JavaScript
- 浏览器 WebSocket API
- 浏览器 WebRTC API
- 浏览器音频设备管理 API

### 测试
- Python
- Playwright（用于自动化测试测试页面连接能力）

---

## 3. 项目目标与实际定位

### 3.1 当前项目实际用途
当前项目是一个 **WebRTC 语音通话信令服务**，而不是完整媒体服务器。

它主要解决的是：
1. Web 页面如何找到目标 ESP32+4G 设备；
2. Web 与 ESP32+4G 设备如何交换 WebRTC 建连所需的信令；
3. 如何通过 MQTT 给设备发送 OTA、版本查询等控制类消息；
4. 如何将设备上报的信息回传给 Web 页面；
5. 如何保留一份信令日志，便于排障。

### 3.2 关键通信关系
- **浏览器 ⇄ 服务端**：WebSocket，地址默认 `/signaling`
- **服务端 ⇄ MQTT Broker**：订阅设备上行主题，向设备下行主题发布消息
- **浏览器 ⇄ 设备**：不直接通信，依赖服务端中转信令

### 3.3 与 ESP32+4G 设备端的关系
**重要**：本项目是配套 ESP32+4G 设备端的服务端部分。

ESP32 设备端代码位于：
- 父目录的 `main/` 目录
- 包含完整的 ESP32 固件代码
- 使用 4G 模组（ML307）进行网络通信
- 通过 MQTT 与本服务端交互
- 基于门铃项目改造，现已演化为通用 WebRTC 语音通话方案

完整系统架构：
```
ESP32+4G 设备 (main/) ⇄ MQTT Broker ⇄ 本服务 (audio_server/) ⇄ WebSocket ⇄ 浏览器
```

### 3.4 应用场景
- 远程语音对讲
- 实时语音通话
- 物联网设备远程控制
- 其他需要 ESP32+4G 进行语音通信的场景

---

## 4. 目录结构说明

```text
audio_server/
├─ pom.xml                              # Maven 配置
├─ test_webrtc.py                       # Playwright 自动化测试脚本
├─ resources/
│  └─ signaling.log                     # 信令持久化日志（运行时写入）
├─ src/
│  └─ main/
│     ├─ java/com/youkong/audio_server/
│     │  ├─ VideoTestApplication.java   # Spring Boot 启动入口
│     │  ├─ config/
│     │  │  ├─ MqttConfig.java          # MQTT 收发配置
│     │  │  ├─ ServerInfoPrinter.java   # 服务信息打印（若使用）
│     │  │  └─ WebSocketConfig.java     # WebSocket 路径注册
│     │  ├─ controller/
│     │  │  └─ MqttTestController.java  # MQTT 测试接口
│     │  ├─ dto/
│     │  │  └─ SignalingMessage.java    # 信令消息 DTO
│     │  ├─ handler/
│     │  │  └─ SignalingWebSocketHandler.java # WebSocket 信令入口
│     │  ├─ service/
│     │  │  ├─ MqttSignalingService.java      # MQTT 信令核心服务
│     │  │  └─ WebSocketSessionManager.java   # WebSocket 会话管理
│     │  └─ util/
│     │     └─ MqttSender.java          # 简单 MQTT 发送工具
│     └─ resources/
│        ├─ application.yml             # 运行配置
│        ├─ static/
│        │  ├─ index.html               # WebRTC 测试主页面
│        │  ├─ index2.html              # 另一个静态页面（如有联调用途）
│        │  └─ index.css                # 页面样式
│        ├─ ssleye2024092417465723.jks  # 证书/密钥文件
│        └─ tomcat_https.keystore       # HTTPS keystore
└─ target/                              # Maven 构建输出目录
```

---

## 5. 启动方式

## 5.1 基本启动
这是一个标准 Maven/Spring Boot 项目。

常见启动方式：

```bash
mvn spring-boot:run
```

或先打包：

```bash
mvn clean package
java -jar target/demo-0.0.1-SNAPSHOT.jar
```

### 5.2 默认服务端口
配置文件 `src/main/resources/application.yml` 中：

- `server.port: 8080`

因此默认访问地址：

- Web 页面：`http://localhost:8080`
- WebSocket：`ws://localhost:8080/signaling`

---

## 6. 核心配置说明

配置文件位置：

```text
src/main/resources/application.yml
```

### 6.1 Web 服务配置
- `server.port`：Spring Boot 服务端口，当前为 `8080`

### 6.2 MQTT 配置
- `spring.mqtt.broker-url`：MQTT Broker 地址
- `spring.mqtt.client-id`：客户端 ID
- `spring.mqtt.username/password`：认证信息
- `spring.mqtt.connection-timeout`：连接超时
- `spring.mqtt.keep-alive-interval`：保活间隔
- `spring.mqtt.clean-session`：是否清理会话
- `spring.mqtt.default-topics`：默认主题（测试接口可能用到）
- `spring.mqtt.qos`：MQTT QoS

### 6.3 业务信令配置
- `signaling.project`：项目标识，用于拼装 MQTT 主题
- `signaling.persistence.enabled`：是否持久化信令日志
- `signaling.persistence.file`：日志文件路径

### 6.4 ICE 配置
- `ice.servers`：ICE/STUN/TURN 服务器配置
- 若为空，则代码中会回退到内置默认值

### 6.5 OTA 配置
- `ota.server-url`：OTA 下载地址
- `ota.target-version`：目标版本号
- `ota.md5`：固件校验值

---

## 7. 架构总览

## 7.1 数据流向

### Web 端发起信令时
1. 浏览器通过 WebSocket 连接 `/signaling`
2. 浏览器发送 `register` 注册自己的设备/会话标识
3. 浏览器发送 `offer / answer / candidate / bye / ota / version_query` 等消息
4. `SignalingWebSocketHandler` 接收消息
5. `MqttSignalingService.forwardToEsp32()` 将消息转发到对应设备 MQTT 下行主题
6. ESP32 接收并处理

### 设备上报信令时
1. ESP32 向 MQTT 上行主题发布消息
2. `MqttConfig` 中的入站 adapter 订阅并接收消息
3. `MqttSignalingService.handleMqttMessage()` 解析消息
4. 根据消息类型转发给指定 WebSocket 会话或广播给 Web 端

---

## 8. 关键类说明

## 8.1 `VideoTestApplication.java`
启动入口类。

职责：
- 启动 Spring Boot 应用
- 开启调度能力（`@EnableScheduling`）

说明：
- 当前代码中未看到特别复杂的调度逻辑，但保留了调度开关。

---

## 8.2 `WebSocketConfig.java`
WebSocket 注册配置。

主要行为：
- 将 `SignalingWebSocketHandler` 挂载到 `/signaling`
- 允许跨域 `setAllowedOrigins("*")`

结论：
- 所有浏览器侧信令入口统一走 `/signaling`

---

## 8.3 `SignalingWebSocketHandler.java`
这是 **WebSocket 侧的核心入口类**。

主要职责：
- 处理 WebSocket 建连
- 维护 `WebSocketSession -> sessionId` 映射
- 接收浏览器发来的信令 JSON
- 校验并补充消息字段
- 按消息类型分发处理
- 将需要发给 ESP32 的消息转给 `MqttSignalingService`

### 支持的消息类型
- `register`
- `offer`
- `answer`
- `candidate`
- `bye`
- `reject`
- `timeout`
- `ice_request`
- `customized`
- `version_query`
- `ota`

### 重要行为
1. **连接成功后自动发送 `connected`**
2. **register 时绑定 deviceId 与 session**
3. **offer/answer/candidate 等转发到 MQTT**
4. **ice_request 时直接返回 ICE 列表给 Web 端**
5. **会自动把 OTA 配置字段写入消息**
   - `url`
   - `version`
   - `md5`

### AI 维护提示
如果后续要新增信令类型，通常要同时修改：
- `SignalingWebSocketHandler.handleSignalingMessage()`
- `MqttSignalingService.handleMqttMessage()`
- `SignalingMessage.isValid()`
- 前端 `index.html` 的消息处理逻辑

---

## 8.4 `WebSocketSessionManager.java`
这是 **WebSocket 会话状态管理器**。

维护了三类核心映射：
- `sessionId -> WebSocketSession`
- `deviceId -> sessionId`
- `sessionId -> deviceId`

主要能力：
- 注册会话
- 绑定设备与会话
- 根据设备 ID 找到 WebSocket 会话并发消息
- 广播消息到所有会话
- 定时清理失效会话

### 适用场景
设备通过 MQTT 上报消息时，服务端需要找到对应 Web 端会话，把消息推送回去。

---

## 8.5 `MqttConfig.java`
这是 **MQTT 接入配置中心**。

主要职责：
- 创建 MQTT 连接参数
- 创建 MQTT client factory
- 配置 MQTT 入站通道（订阅）
- 配置 MQTT 出站通道（发布）
- 收到 MQTT 消息后交给 `MqttSignalingService`

### 当前订阅主题
代码中动态构造：

```text
/voice/{project}/+/up
```

含义：
- 订阅当前项目下所有设备的上行消息

### 当前下行主题格式
发送给设备时：

```text
/voice/{project}/{deviceId}/down
```

---

## 8.6 `MqttSignalingService.java`
这是项目中最核心的业务类之一，负责 **MQTT 与 WebSocket 之间的信令桥接**。

主要职责：
- 初始化 MQTT 发布客户端
- 接收并处理 MQTT 上行消息
- 将信令写入日志文件
- 处理 ICE 请求
- 处理 WebRTC 信令转发
- 处理自定义消息广播/单播
- 维护通话会话状态
- 保存设备版本信息
- 发送 OTA / 版本查询指令

### 内部关注点
#### 1）消息接收入口
- `handleMqttMessage(String topic, String payload)`

#### 2）支持处理的 MQTT 消息类型
- `ice_request`
- `offer`
- `answer`
- `candidate`
- `bye`
- `reject`
- `timeout`
- `customized`
- `ring`
- `version_report`

#### 3）设备版本管理
- 使用 `deviceVersions` 维护设备版本缓存
- `handleVersionReport()` 处理版本上报
- `queryVersion()` 向设备发送版本查询命令

#### 4）OTA 能力
- `manualOtaUpgrade()` 手动向设备推送 OTA
- WebSocket 端也可通过 `ota` 类型消息转发 OTA 指令

#### 5）信令持久化
- 通过 `persistSignaling()` 将 UP / DOWN 信令写入文本日志
- 默认文件：`resources/signaling.log`

### AI 维护提示
这是后续扩展业务时最容易集中修改的类：
- 新增消息类型
- 调整主题规则
- 增加设备状态缓存
- 增加消息审计/回放能力
- 做版本管理和 OTA 策略优化

---

## 8.7 `SignalingMessage.java`
这是整个项目的统一信令 DTO。

主要字段：
- `type`：消息类型
- `target`：目标设备或目标会话
- `from`：发送方
- `timestamp`：时间戳
- `sdp`：WebRTC SDP
- `candidate`：ICE candidate
- `iceServers`：ICE 服务器列表
- `data`：附加数据
- `url`：OTA 下载地址
- `md5`：OTA 校验值
- `version`：版本号

### 重要逻辑
- `isValid()`：按不同消息类型做最小校验
- `getDownTopic(project)`：生成设备下行主题

### 注意点
`target` 字段带有默认值 `web_client_001`，这意味着：
- 某些未显式传递 target 的消息可能会沿用默认值；
- 后续排查“消息被发到默认对象”时，要重点看这里。

---

## 8.8 `MqttTestController.java`
提供一个简单的 HTTP 测试接口，用于手动发送 MQTT 消息。

接口路径：

```text
GET /mqtt/send
```

参数：
- `topic`：可选
- `message`：必填

用途：
- 本地联调时快速验证 MQTT 发送链路
- 不建议作为正式业务接口长期扩展

---

## 8.9 `src/main/resources/static/index.html`
这是当前项目最重要的前端联调页面。

主要能力：
- 配置 WebSocket 连接地址
- 输入本端设备 ID 和目标设备 ID
- 建立 WebSocket 连接并注册
- 发起 WebRTC 呼叫
- 接听/挂断/拒接
- 请求 ICE 服务器配置
- 枚举音频输入输出设备
- 简单音量柱状显示
- 导出日志

### 前端消息处理范围
支持接收：
- `connected`
- `register_response`
- `ice_response`
- `offer`
- `answer`
- `candidate`
- `bye`
- `reject`
- `timeout`
- `error`

### 前端定位
它更偏向：
- 联调页面
- 演示页面
- 人工测试页面

而不是正式生产 UI。

---

## 9. 信令协议梳理

以下是从代码中整理出的消息语义。

## 9.1 Web 端常发消息

### `register`
用途：WebSocket 会话注册自身设备 ID

关键字段：
- `type=register`
- `from`
- `timestamp`

### `offer`
用途：发起 WebRTC 呼叫

关键字段：
- `type=offer`
- `target`
- `from`
- `timestamp`
- `sdp`

### `answer`
用途：应答 WebRTC 呼叫

### `candidate`
用途：交换 ICE 候选

### `bye`
用途：挂断

### `reject`
用途：拒接

### `ice_request`
用途：请求 ICE/TURN/STUN 配置

### `version_query`
用途：查询设备版本

### `ota`
用途：下发 OTA 升级命令

### `customized`
用途：业务自定义扩展

---

## 9.2 设备侧常发消息

### `offer / answer / candidate`
表示设备侧参与 WebRTC 建连

### `ring`
表示设备通知来电/振铃类事件

### `version_report`
表示设备上报当前版本号

### `customized`
表示设备发来的自定义业务消息

---

## 10. MQTT 主题规则

从代码可知，当前默认主题规则为：

### 10.1 设备上行主题

```text
/voice/{project}/{deviceId}/up
```

例如：

```text
/voice/project/esp32_001/up
```

### 10.2 设备下行主题

```text
/voice/{project}/{deviceId}/down
```

例如：

```text
/voice/project/esp32_001/down
```

### 10.3 服务端订阅模式

```text
/voice/{project}/+/up
```

表示服务端会订阅该项目下所有设备的上行消息。

---

## 11. 运行时状态与数据

## 11.1 WebSocket 会话状态
由 `WebSocketSessionManager` 管理，主要是内存态，不持久化。

## 11.2 通话状态
由 `MqttSignalingService.callSessions` 管理，当前也是内存态。

说明：
- 服务重启后丢失
- 当前更适合开发联调和轻量场景

## 11.3 设备版本缓存
由 `deviceVersions` 维护，也是内存态。

## 11.4 信令日志
写入：

```text
resources/signaling.log
```

日志格式大致包含：
- 时间戳
- UP / DOWN 方向
- Topic
- Payload

---

## 12. 前端联调方法

### 12.1 打开页面
启动服务后直接访问：

```text
http://localhost:8080
```

### 12.2 基本操作流程
1. 输入服务器地址和端口
2. 输入本端设备 ID（默认 `web_client_001`）
3. 点击“连接”建立 WebSocket
4. 输入目标 ESP32 设备 ID（默认 `esp32_001`）
5. 点击“发起通话”发送 `offer`
6. 观察信令日志和设备响应

### 12.3 调试重点
- WebSocket 是否成功连接 `/signaling`
- `register` 是否返回 `register_response`
- 目标设备 ID 是否正确
- MQTT Broker 是否可连接
- 设备是否订阅正确下行主题
- 浏览器是否授予麦克风权限

---

## 13. 自动化测试脚本说明

文件：`test_webrtc.py`

功能：
- 用 Playwright 打开 `http://localhost:8080`
- 查找并点击“连接”按钮
- 等待连接建立
- 检查页面状态是否变成“已连接”

定位：
- 这是一个 **页面连通性 / WebSocket 连接成功** 的自动化验证脚本
- 不是完整的端到端 WebRTC 通话自动化测试

运行前需要安装：
- `playwright`
- Chromium 浏览器驱动

---

## 14. 当前项目中的关键假设

后续 AI 接手时，建议优先记住以下假设：

1. **Web 端是主动连接的一方**
   - 先连 WebSocket
   - 再注册 deviceId

2. **ESP32 不走 WebSocket，而走 MQTT**
   - 设备上行：`.../up`
   - 设备下行：`.../down`

3. **服务端只做信令桥接，不直接承载媒体转发**
   - 媒体流最终由 WebRTC peer 间建立

4. **很多业务命令都复用了同一个 DTO：`SignalingMessage`**
   - 新增业务类型时不要单独发明一套消息结构，优先复用现有 DTO

5. **当前很多状态在内存中**
   - 服务重启后丢失是预期行为

---

## 15. 已发现的实现特征与维护注意事项

以下内容不是“必须马上修改”的问题，而是后续 AI / 开发者阅读代码时需要重点留意的地方。

### 15.1 `target` 默认值可能影响路由
`SignalingMessage.target` 默认是 `web_client_001`。
这会带来一个维护风险：
- 某些本应未指定目标的消息，可能被默认路由到固定对象。

### 15.2 ICE 默认值写在代码里
当 `ice.servers` 为空时，`MqttSignalingService.parseIceServers()` 会回退到内置 STUN/TURN 配置。
这意味着：
- 真实部署时最好确认这些服务是否仍可用；
- 若联调异常，要同时检查配置文件和代码默认值。

### 15.3 OTA 参数会在 WebSocket 收到消息时被自动补入
`SignalingWebSocketHandler` 收到消息后会统一写入：
- `url`
- `version`
- `md5`

因此如果前端发 `ota` 消息但字段与配置不一致，最终下发给设备的内容可能受服务端配置覆盖。

### 15.4 状态管理主要是内存态
当前：
- 会话绑定
- 通话状态
- 设备版本
都不是数据库持久化。

如果未来要支持：
- 多实例部署
- 服务重启恢复
- 历史查询
- 在线状态面板
则需要考虑持久化或集中式缓存。

### 15.5 `target/` 是构建产物目录
该目录包含：
- 编译 class
- 打包 jar
- 复制后的资源文件

后续 AI 在分析项目时，应优先阅读：
- `src/main/java`
- `src/main/resources`

不要把 `target/classes` 里的文件当成源码修改入口。

---

## 16. 后续 AI 最常见的修改入口

如果未来需求是以下类型，通常应从这些文件入手：

### 新增一种信令类型
优先查看：
- `src/main/java/com/youkong/audio_server/dto/SignalingMessage.java`
- `src/main/java/com/youkong/audio_server/handler/SignalingWebSocketHandler.java`
- `src/main/java/com/youkong/audio_server/service/MqttSignalingService.java`
- `src/main/resources/static/index.html`

### 调整 MQTT 主题规则
优先查看：
- `src/main/java/com/youkong/audio_server/config/MqttConfig.java`
- `src/main/java/com/youkong/audio_server/service/MqttSignalingService.java`

### 调整 WebSocket 路径
优先查看：
- `src/main/java/com/youkong/audio_server/config/WebSocketConfig.java`
- `src/main/resources/static/index.html`

### 调整前端联调页面
优先查看：
- `src/main/resources/static/index.html`
- `src/main/resources/static/index.css`

### 调整 OTA/版本管理
优先查看：
- `src/main/resources/application.yml`
- `src/main/java/com/youkong/audio_server/handler/SignalingWebSocketHandler.java`
- `src/main/java/com/youkong/audio_server/service/MqttSignalingService.java`

### 增强日志/排障能力
优先查看：
- `src/main/java/com/youkong/audio_server/service/MqttSignalingService.java`
- `resources/signaling.log`

---

## 17. 建议的阅读顺序（给后续 AI）

如果后续 AI 需要快速理解本项目，建议按以下顺序阅读：

1. `pom.xml`
   - 确认技术栈和依赖
2. `src/main/resources/application.yml`
   - 确认运行配置、MQTT、OTA、ICE
3. `src/main/java/com/youkong/audio_server/config/WebSocketConfig.java`
   - 确认 WebSocket 入口
4. `src/main/java/com/youkong/audio_server/handler/SignalingWebSocketHandler.java`
   - 理解 Web 端消息如何进入系统
5. `src/main/java/com/youkong/audio_server/service/WebSocketSessionManager.java`
   - 理解会话绑定和消息回推
6. `src/main/java/com/youkong/audio_server/config/MqttConfig.java`
   - 理解 MQTT 订阅/发布配置
7. `src/main/java/com/youkong/audio_server/service/MqttSignalingService.java`
   - 理解全部核心业务逻辑
8. `src/main/java/com/youkong/audio_server/dto/SignalingMessage.java`
   - 理解消息结构
9. `src/main/resources/static/index.html`
   - 理解前端如何发消息、怎么联调
10. `test_webrtc.py`
   - 理解现有自动化测试覆盖范围

---

## 18. 一句话总结

这是一个 **面向 Web 与 ESP32 设备之间 WebRTC 信令中转的 Spring Boot 服务**，通过 **WebSocket + MQTT** 把浏览器侧联调页面和设备侧消息通道串起来，并附带 **ICE 配置、OTA 指令、版本上报、信令日志** 等辅助能力。

---

## 19. 给后续 AI 的快速提示

如果你是后续接手这个项目的 AI，请优先记住：

- 后端核心不是媒体处理，而是 **信令桥接**；
- Web 端入口在 `/signaling`；
- 设备入口在 MQTT 主题 `/voice/{project}/{deviceId}/up`；
- 最核心逻辑集中在：
  - `SignalingWebSocketHandler`
  - `MqttSignalingService`
  - `WebSocketSessionManager`
  - `SignalingMessage`
- 前端联调主页面是 `src/main/resources/static/index.html`；
- 如果出现“消息没到对端”，优先排查：
  1. target/deviceId 是否正确
  2. WebSocket register 是否完成
  3. MQTT broker 是否联通
  4. MQTT 主题规则是否一致
  5. DTO 校验 `isValid()` 是否拦截了消息

---

## 20. 文档维护建议

当项目发生以下变化时，建议同步更新本文件：
- 新增消息类型
- 修改 MQTT 主题规则
- 修改 WebSocket 路径
- 引入数据库/Redis 等持久化能力
- 增加新的前端页面
- 调整 OTA / ICE / 版本管理逻辑

如果后续要继续让 AI 高效接手，建议始终保持本文件与当前实现一致。
