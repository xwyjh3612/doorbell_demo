# 项目工作约定

## 安卓依赖存放

- 通用安卓工具、依赖与共享缓存统一放在 `F:\android`，复用已有版本。
- Android SDK/NDK：`F:\android\sdk`。
- 安卓构建使用的JDK：`F:\android\Java`，本项目默认 `jdk-17.0.11`。
- Gradle发行版：`F:\android\gradle`，本项目默认 `8.10.2`。
- Gradle共享依赖缓存与Wrapper下载：`F:\android\repository\gradle`；已有共享Maven库位于 `F:\android\repository\maven`。
- 不在C盘用户缓存、附件目录、项目build目录等位置另装通用安卓工具或另建共享安卓依赖缓存。
- 项目专用代码、Gradle Wrapper配置、local.properties、项目缓存、构建中间文件、APK和项目专用签名配置留在项目本地。不要把项目专用文件塞入共享依赖目录。
- 默认通过 `tools/build-android.ps1` 构建；直接调用Gradle时也要明确设置共享 `GRADLE_USER_HOME`。
- 变更路径前检查现有工具与缓存，避免重复下载。移动已有目录前核对使用状态和目标路径，不删除用户已有依赖。

## 固件约束

- 产品名称是语音对讲。
- ESP32官方通信协议与音频主动丢旧包策略保持现有约定，不能因工具链或目录整理而修改。
