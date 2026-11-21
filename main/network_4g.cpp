#include "esp_log.h"
#include "at_modem.h"
#include "network_4g.h"
#include "mqtt_signaling.h"
#include "app_config.h"
#include <atomic>
#include <mutex>

#include <sys/socket.h>
#include <arpa/inet.h>
#include <netdb.h>

static const char *TAG = "network_4g";

namespace Network4g {
    // 将 modem 声明为命名空间级别的静态常量指针
    // 使用 nullptr 初始化，在 init() 函数中完成实际赋值

    static std::unique_ptr<AtModem> modem = nullptr;

    static std::unique_ptr<Mqtt> mqtt = nullptr;
    static std::atomic<Mqtt *> published_mqtt{nullptr};
    static std::mutex mqtt_init_mutex;
    static std::atomic<bool> initialized{false};
    static std::atomic<bool> mqtt_restart_pending{false};

    void init(void) {
        ESP_LOGI(TAG, "开始检测4G网络");
        // 自动检测并初始化模组
        modem = AtModem::Detect(GPIO_NUM_17, GPIO_NUM_18, GPIO_NUM_4, 921600);


        if (!modem) {
            ESP_LOGE(TAG, "模组检测失败");
            return;
        }

        // Observe only registration/boot control URCs. Never enable a raw AT
        // dump: media packets and credentials share this UART.
        modem->GetAtUart()->RegisterUrcCallback([](const std::string& command,
                const std::vector<AtArgumentValue>& arguments) {
            if (command == "MATREADY") {
                static unsigned boot_notices = 0;
                ESP_LOGW(TAG, "MODEM_EVT MATREADY boot_notice=%u", ++boot_notices);
            } else if (command == "CEREG" || command == "MIPCALL") {
                int p0 = arguments.size() > 0 && arguments[0].type == AtArgumentValue::Type::Int
                             ? arguments[0].int_value : -1;
                int p1 = arguments.size() > 1 && arguments[1].type == AtArgumentValue::Type::Int
                             ? arguments[1].int_value : -1;
                ESP_LOGI(TAG, "MODEM_EVT %s argc=%u p0=%d p1=%d", command.c_str(),
                         (unsigned)arguments.size(), p0, p1);
            }
        });

        // 设置网络状态回调
        modem->OnNetworkStateChanged([](bool ready) {
            ESP_LOGI(TAG, "网络状态: %s", ready ? "已连接" : "已断开");
            if (ready && initialized.exchange(true) && !mqtt_restart_pending.exchange(true)) {
                // 网络连接成功，延迟重启 MQTT 信令，避免干扰网络检测
                ESP_LOGI(TAG, "网络已恢复，延迟重启MQTT信令...");
                TaskHandle_t task_handle;
                BaseType_t created = xTaskCreate([](void* arg) {
                    ESP_LOGI(TAG, "2秒后开始初始化mqtt");
                    vTaskDelay(pdMS_TO_TICKS(2000));  // 等待 2 秒让网络完全恢复
                    ESP_LOGI(TAG, "开始初始化MQTT...");
                    initMqtt();
                    mqtt_sig_restart();
                    mqtt_restart_pending.store(false);
                    vTaskDelete(NULL);
                }, "mqtt_restart", 8192, NULL, 5, &task_handle);
                if (created != pdPASS) {
                    mqtt_restart_pending.store(false);
                    ESP_LOGE(TAG, "无法创建MQTT恢复任务");
                }
            }
        });

        // 等待网络就绪
        NetworkStatus status = modem->WaitForNetworkReady(30000);
        if (status != NetworkStatus::Ready) {
            ESP_LOGE(TAG, "网络连接失败");
            return;
        }

        // 打印模组信息
        ESP_LOGI(TAG, "模组版本: %s", modem->GetModuleRevision().c_str());
        ESP_LOGI(TAG, "IMEI: %s", modem->GetImei().c_str());
        ESP_LOGI(TAG, "ICCID: %s", modem->GetIccid().c_str());
        ESP_LOGI(TAG, "运营商: %s", modem->GetCarrierName().c_str());
        ESP_LOGI(TAG, "信号强度: %d", modem->GetCsq());
    }

    void initMqtt(){
        std::lock_guard<std::mutex> lock(mqtt_init_mutex);
        // 先检查 modem 是否初始化成功，避免空指针访问
        if (!modem) {
            ESP_LOGE(TAG, "模组未初始化，无法执行 HTTP 请求");
            return;
        }

        // Readers retain this address. Recovery reconnects the same client;
        // replacing it can delete an event group while telemetry is using it.
        if (!mqtt) {
            mqtt = modem->CreateMqtt(0);
            if (!mqtt) {
                ESP_LOGE(TAG, "无法创建MQTT客户端");
                return;
            }

            // 设置回调函数
            mqtt->OnConnected([]() {
                ESP_LOGI(TAG, "MQTT 连接成功");
            });

            mqtt->OnDisconnected([]() {
                ESP_LOGI(TAG, "MQTT 连接断开");
            });
            published_mqtt.store(mqtt.get(), std::memory_order_release);
        }

/*	    mqtt->OnMessage([](const std::string& topic, const std::string& payload) {
	        ESP_LOGI(TAG, "收到消息 [%s]: %s", topic.c_str(), payload.c_str());
	    });*/

	    // 连接到 MQTT 代理
	    app_config_t* cfg = app_config_get();
	    if (mqtt->Connect(cfg->mqtt_host, cfg->mqtt_port, cfg->mqtt_user, cfg->mqtt_password, "")) {
	        // 订阅主题
	        mqtt->Subscribe("test/esp32/message");

	        // 发布消息
	        mqtt->Publish("test/esp32/message", "Hello from ESP32!");

	        ESP_LOGI(TAG, "订阅主题并发送消息");
	        // 等待一段时间接收消息
	        //vTaskDelay(pdMS_TO_TICKS(5000));

	        // 发布消息
	        mqtt->Publish("test/esp32/hello", "Hello from ESP32111!");
	        //先不断开
	        //mqtt->Disconnect();
	    } else {
	        ESP_LOGE(TAG, "MQTT 连接失败");
	    }

    }

    // 对外提供智能指针的原始指针（供外部调用）
    AtModem* GetModemInstance() {
        // 只有智能指针有效时才返回原始指针
        return modem ? modem.get() : nullptr;
    }

    // 对外提供智能指针的原始指针（供外部调用）
    Mqtt* GetMqttInstance() {
        return published_mqtt.load(std::memory_order_acquire);
    }


    std::string resolveDomain(const char* domain) {
        if (!modem) {
            ESP_LOGE(TAG, "模组未初始化");
            return "";
        }

        auto at_uart = modem->GetAtUart();
        if (!at_uart) {
            ESP_LOGE(TAG, "AT UART未初始化");
            return "";
        }

        static std::string g_dns_result;
        static bool g_dns_received = false;
        g_dns_result.clear();
        g_dns_received = false;

        auto callback_it = at_uart->RegisterUrcCallback(
            [domain, &g_dns_result, &g_dns_received](const std::string& command, const std::vector<AtArgumentValue>& arguments) {
                if (command == "MDNSGIP" && !arguments.empty()) {
                    std::string result_domain = arguments[0].string_value;
                    ESP_LOGI(TAG, "DNS URC收到: %s", result_domain.c_str());
                    if (arguments.size() >= 2) {
                        g_dns_result = arguments[1].string_value;
                        ESP_LOGI(TAG, "DNS解析结果: %s", g_dns_result.c_str());
                    }
                    g_dns_received = true;
                }
            }
        );

        std::string cmd = "AT+MDNSGIP=\"" + std::string(domain) + "\"";
        bool success = at_uart->SendCommand(cmd, 5000, true);

        if (!success) {
            ESP_LOGE(TAG, "DNS解析命令发送失败");
            at_uart->UnregisterUrcCallback(callback_it);
            return "";
        }

        int wait_count = 0;
        while (!g_dns_received && wait_count < 50) {
            vTaskDelay(pdMS_TO_TICKS(100));
            wait_count++;
        }

        at_uart->UnregisterUrcCallback(callback_it);

        if (g_dns_result.empty()) {
            ESP_LOGE(TAG, "未收到DNS解析结果");
            return "";
        }

        struct in_addr in;
        if (inet_pton(AF_INET, g_dns_result.c_str(), &in) != 1) {
            ESP_LOGE(TAG, "解析结果不是有效IPv4: %s", g_dns_result.c_str());
            return "";
        }

        ESP_LOGI(TAG, "域名 %s 解析结果: %s", domain, g_dns_result.c_str());
        return g_dns_result;
    }
}
