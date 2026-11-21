#include "ml307_mqtt.h"
#include <esp_log.h>

static const char *TAG = "Ml307Mqtt";

Ml307Mqtt::Ml307Mqtt(std::shared_ptr<AtUart> at_uart, int mqtt_id) : at_uart_(at_uart), mqtt_id_(mqtt_id) {
    event_group_handle_ = xEventGroupCreate();

    urc_callback_it_ = at_uart_->RegisterUrcCallback([this](const std::string& command, const std::vector<AtArgumentValue>& arguments) {
        HandleUrc(command, arguments);
    });
}

void Ml307Mqtt::HandleUrc(const std::string& command, const std::vector<AtArgumentValue>& arguments) {
        if (command != "MQTTURC" && command != "MQTTSTATE" && command != "MATREADY") return;
        // Callbacks may be installed concurrently with UART reception. Copy
        // them under a separate mutex; invoke outside it. They must not issue
        // AT commands on this receiver (AtUart still holds its callback lock).
        std::function<void()> connected_callback, disconnected_callback;
        std::function<void(const std::string&, const std::string&)> message_callback;
        std::function<void(const std::string&)> error_callback;
        {
            std::lock_guard<std::mutex> lock(callback_mutex_);
            connected_callback = on_connected_callback_;
            disconnected_callback = on_disconnected_callback_;
            message_callback = on_message_callback_;
            error_callback = on_error_callback_;
        }
        if (command == "MATREADY") {
            message_payload_.clear();
            if (connected_.exchange(false) && disconnected_callback) disconnected_callback();
            xEventGroupClearBits(event_group_handle_, MQTT_CONNECTED_EVENT | MQTT_INITIALIZED_EVENT);
            xEventGroupSetBits(event_group_handle_, MQTT_DISCONNECTED_EVENT);
        } else if (command == "MQTTURC" && arguments.size() >= 2) {
            if (arguments[1].int_value == mqtt_id_) {
                auto type = arguments[0].string_value;
                if (type == "conn" && arguments.size() >= 3) {
                    int error_code = arguments[2].int_value;
                    last_error_ = error_code;  // Store error code
                    if (error_code == 0) {
                        if (!connected_.exchange(true)) {
                            if (connected_callback) {
                                connected_callback();
                            }
                        }
                        xEventGroupSetBits(event_group_handle_, MQTT_CONNECTED_EVENT);
                    } else {
                        if (connected_.exchange(false)) {
                            if (disconnected_callback) {
                                disconnected_callback();
                            }
                        }
                        xEventGroupSetBits(event_group_handle_, MQTT_DISCONNECTED_EVENT);
                    }
                    if (error_code == 5 || error_code == 6) {
                        auto error_message = ErrorToString(error_code);
                        ESP_LOGW(TAG, "MQTT error occurred: %s", error_message.c_str());
                        if (error_callback) {
                            error_callback(error_message);
                        }
                    }
                } else if (type == "suback") {
                } else if (type == "publish" && arguments.size() >= 7) {
                    auto topic = arguments[3].string_value;
                    if (arguments[4].int_value == arguments[5].int_value) {
                        if (message_callback) {
                            message_callback(topic, at_uart_->DecodeHex(arguments[6].string_value));
                        }
                    } else {
                        message_payload_.append(at_uart_->DecodeHex(arguments[6].string_value));
                        if (message_payload_.size() >= arguments[4].int_value && message_callback) {
                            message_callback(topic, message_payload_);
                            message_payload_.clear();
                        }
                    }
                } else {
                    ESP_LOGI(TAG, "unhandled MQTT event: %s", type.c_str());
                }
            }
        } else if (command == "MQTTSTATE" && arguments.size() == 1) {
            connected_ = arguments[0].int_value == 2;
            xEventGroupSetBits(event_group_handle_, MQTT_INITIALIZED_EVENT);
        }
}

Ml307Mqtt::~Ml307Mqtt() {
    at_uart_->UnregisterUrcCallback(urc_callback_it_);
    vEventGroupDelete(event_group_handle_);
}

bool Ml307Mqtt::Connect(const std::string broker_address, int broker_port, const std::string client_id, const std::string username, const std::string password) {
    EventBits_t bits;
    if (!QueryConnectionState()) {
        return false;
    }
    if (IsConnected()) {
        // 断开之前的连接
        xEventGroupClearBits(event_group_handle_, MQTT_DISCONNECTED_EVENT);
        Disconnect();
        bits = xEventGroupWaitBits(event_group_handle_, MQTT_DISCONNECTED_EVENT, pdTRUE, pdFALSE, pdMS_TO_TICKS(MQTT_CONNECT_TIMEOUT_MS));
        if (!(bits & MQTT_DISCONNECTED_EVENT)) {
            ESP_LOGE(TAG, "Failed to disconnect from previous connection");
            return false;
        }
    }

    if (broker_port == 8883) {
        if (!at_uart_->SendCommand(std::string("AT+MQTTCFG=\"ssl\",") + std::to_string(mqtt_id_) + ",1")) {
            ESP_LOGE(TAG, "Failed to set MQTT to use SSL");
            return false;
        }
    }

    // Set clean session
    if (!at_uart_->SendCommand(std::string("AT+MQTTCFG=\"clean\",") + std::to_string(mqtt_id_) + ",1")) {
        ESP_LOGE(TAG, "Failed to set MQTT clean session");
        return false;
    }

    // Set keep alive and ping interval both to the same value
    if (!at_uart_->SendCommand(std::string("AT+MQTTCFG=\"keepalive\",") + std::to_string(mqtt_id_) + "," + std::to_string(keep_alive_seconds_))) {
        ESP_LOGE(TAG, "Failed to set MQTT keepalive interval");
        return false;
    }
    if (!at_uart_->SendCommand(std::string("AT+MQTTCFG=\"pingreq\",") + std::to_string(mqtt_id_) + "," + std::to_string(keep_alive_seconds_))) {
        ESP_LOGE(TAG, "Failed to set MQTT ping interval");
        return false;
    }

    // Set HEX encoding (ASCII for sending, HEX for receiving)
    if (!at_uart_->SendCommand("AT+MQTTCFG=\"encoding\"," + std::to_string(mqtt_id_) + ",0,1")) {
        ESP_LOGE(TAG, "Failed to set MQTT to use HEX encoding");
        return false;
    }

    xEventGroupClearBits(event_group_handle_, MQTT_CONNECTED_EVENT | MQTT_DISCONNECTED_EVENT);
    // 创建MQTT连接
    std::string command = "AT+MQTTCONN=" + std::to_string(mqtt_id_) + ",\"" + broker_address + "\"," + std::to_string(broker_port) + ",\"" + client_id + "\",\"" + username + "\",\"" + password + "\"";
    if (!at_uart_->SendCommand(command)) {
        ESP_LOGE(TAG, "Failed to create MQTT connection");
        return false;
    }

    // 等待连接完成
    bits = xEventGroupWaitBits(event_group_handle_, MQTT_CONNECTED_EVENT | MQTT_DISCONNECTED_EVENT, pdTRUE, pdFALSE, pdMS_TO_TICKS(MQTT_CONNECT_TIMEOUT_MS));
    if (!(bits & MQTT_CONNECTED_EVENT)) {
        ESP_LOGE(TAG, "Failed to connect to MQTT broker");
        return false;
    }
    return true;
}

bool Ml307Mqtt::IsConnected() {
    // URCs maintain this state. A local readiness check must not occupy the
    // shared media UART or wait ten seconds on every signaling/telemetry call.
    return connected_.load();
}

bool Ml307Mqtt::QueryConnectionState() {
    xEventGroupClearBits(event_group_handle_, MQTT_INITIALIZED_EVENT);
    if (!at_uart_->SendCommand(std::string("AT+MQTTSTATE=") + std::to_string(mqtt_id_))) {
        connected_ = false;
        return false;
    }
    auto bits = xEventGroupWaitBits(event_group_handle_, MQTT_INITIALIZED_EVENT, pdTRUE, pdFALSE, pdMS_TO_TICKS(MQTT_CONNECT_TIMEOUT_MS));
    if (!(bits & MQTT_INITIALIZED_EVENT)) {
        connected_ = false;
        ESP_LOGE(TAG, "Failed to initialize MQTT connection");
        return false;
    }
    return true;
}

void Ml307Mqtt::OnConnected(std::function<void()> callback) {
    std::lock_guard<std::mutex> lock(callback_mutex_);
    on_connected_callback_ = std::move(callback);
}
void Ml307Mqtt::OnDisconnected(std::function<void()> callback) {
    std::lock_guard<std::mutex> lock(callback_mutex_);
    on_disconnected_callback_ = std::move(callback);
}
void Ml307Mqtt::OnMessage(std::function<void(const std::string&, const std::string&)> callback) {
    std::lock_guard<std::mutex> lock(callback_mutex_);
    on_message_callback_ = std::move(callback);
}
void Ml307Mqtt::OnError(std::function<void(const std::string&)> callback) {
    std::lock_guard<std::mutex> lock(callback_mutex_);
    on_error_callback_ = std::move(callback);
}

void Ml307Mqtt::Disconnect() {
    if (!connected_) {
        return;
    }
    at_uart_->SendCommand(std::string("AT+MQTTDISC=") + std::to_string(mqtt_id_));
}

bool Ml307Mqtt::Publish(const std::string topic, const std::string payload, int qos) {
    if (!connected_) {
        return false;
    }
    // If payload size is larger than 64KB, a CME ERROR 601 will be returned.
    std::string command = "AT+MQTTPUB=" + std::to_string(mqtt_id_) + ",\"" + topic + "\",";
    command += std::to_string(qos) + ",0,0,";
    command += std::to_string(payload.size());
    return at_uart_->SendCommandWithData(command, 1000, true, payload.data(), payload.size());
}

bool Ml307Mqtt::Subscribe(const std::string topic, int qos) {
    if (!connected_) {
        return false;
    }
    std::string command = "AT+MQTTSUB=" + std::to_string(mqtt_id_) + ",\"" + topic + "\"," + std::to_string(qos);
    return at_uart_->SendCommand(command);
}

bool Ml307Mqtt::Unsubscribe(const std::string topic) {
    if (!connected_) {
        return false;
    }
    std::string command = "AT+MQTTUNSUB=" + std::to_string(mqtt_id_) + ",\"" + topic + "\"";
    return at_uart_->SendCommand(command);
}

std::string Ml307Mqtt::ErrorToString(int error_code) {
    switch (error_code) {
        case 0:
            return "Connected";
        case 1:
            return "Reconnecting";
        case 2:
            return "Disconnected: User initiated";
        case 3:
            return "Disconnected: Rejected (protocol version, identifier, username or password error)";
        case 4:
            return "Disconnected: Server disconnected";
        case 5:
            return "Disconnected: Ping timeout";
        case 6:
            return "Disconnected: Network error";
        case 255:
            return "Disconnected: Unknown error";
        default:
            return "Unknown error";
    }
}

int Ml307Mqtt::GetLastError() {
    return last_error_;
}
