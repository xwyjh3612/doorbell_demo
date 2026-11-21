#include <atomic>
#include <cassert>
#include <cstdio>
#include <deque>
#include <functional>
#include <list>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

#define ESP_LOGI(...) ((void)0)
#define ESP_LOGE(...) ((void)0)
#define ESP_LOGW(...) ((void)0)
#define BIT0 1
#define BIT1 2
#define BIT2 4
#define pdTRUE true
#define pdFALSE false
#define pdPASS 1
#define pdMS_TO_TICKS(x) (x)
using EventBits_t = unsigned;
using EventGroupHandle_t = unsigned*;
static unsigned deleted_events;
EventGroupHandle_t xEventGroupCreate() { return new unsigned(0); }
void vEventGroupDelete(EventGroupHandle_t group) { ++deleted_events; delete group; }
void xEventGroupSetBits(EventGroupHandle_t group, unsigned bits) { *group |= bits; }
void xEventGroupClearBits(EventGroupHandle_t group, unsigned bits) { *group &= ~bits; }
unsigned xEventGroupWaitBits(EventGroupHandle_t group, unsigned mask, bool clear, bool, unsigned) {
    unsigned bits = *group;
    if (clear) *group &= ~mask;
    return bits & mask;
}
struct AtArgumentValue {
    int int_value = 0;
    std::string string_value;
};
using UrcCallback = std::function<void(const std::string&, const std::vector<AtArgumentValue>&)>;
struct AtUart {
    std::list<UrcCallback> callbacks;
    bool receiving = false, query_fails = false, query_missing = false;
    int state = 3;
    unsigned commands = 0;
    std::list<UrcCallback>::iterator RegisterUrcCallback(UrcCallback callback) {
        return callbacks.insert(callbacks.end(), std::move(callback));
    }
    void UnregisterUrcCallback(std::list<UrcCallback>::iterator it) { callbacks.erase(it); }
    void emit(const std::string& name, const std::vector<AtArgumentValue>& values) {
        receiving = true;
        for (auto& callback : callbacks) callback(name, values);
        receiving = false;
    }
    bool SendCommand(const std::string& command, unsigned = 1000) {
        if (receiving) throw std::logic_error("AT command on locked UART receiver");
        ++commands;
        if (command.starts_with("AT+MQTTSTATE=")) {
            if (query_fails) return false;
            if (!query_missing) emit("MQTTSTATE", {{state, {}}});
        } else if (command.starts_with("AT+MQTTCONN=")) {
            state = 2; emit("MQTTURC", {{0,"conn"},{0,{}},{0,{}}});
        } else if (command.starts_with("AT+MQTTDISC=")) {
            state = 3; emit("MQTTURC", {{0,"conn"},{0,{}},{2,{}}});
        }
        return true;
    }
    bool SendCommandWithData(const std::string& command, unsigned timeout, bool,
                             const char*, size_t) { return SendCommand(command, timeout); }
    std::string DecodeHex(const std::string& data) { return data; }
};
#include "mqtt_interface_under_test.inc"
#include "mqtt_client_header_under_test.inc"
#include "mqtt_client_under_test.inc"

struct app_config_t {
    std::string mqtt_host = "broker.invalid", mqtt_user = "test-client", mqtt_password = "test-user";
    int mqtt_port = 1883;
};
app_config_t* app_config_get() { static app_config_t config; return &config; }
struct TestModem {
    std::shared_ptr<AtUart> uart = std::make_shared<AtUart>();
    unsigned clients_created = 0;
    std::unique_ptr<Mqtt> CreateMqtt(int id) {
        ++clients_created; return std::make_unique<Ml307Mqtt>(uart, id);
    }
};
namespace Network4g {
    static std::unique_ptr<TestModem> modem = std::make_unique<TestModem>();
    static std::unique_ptr<Mqtt> mqtt;
    static std::atomic<Mqtt*> published_mqtt{nullptr};
    static std::mutex mqtt_init_mutex;
    #include "mqtt_network_init_under_test.inc"
    #include "mqtt_network_get_under_test.inc"
}

struct MqttMessage {
    std::string topic, payload;
    enum class Kind { Message, Connected, Disconnected } kind = Kind::Message;
};
static std::deque<MqttMessage*> queued;
static void* mqtt_messages = &queued;
int xQueueSend(void*, MqttMessage** message, int) {
    if (queued.size() >= 16) return 0;
    queued.push_back(*message); return pdPASS;
}
static bool g_mqtt_initialized = false, g_mqtt_connected = false;
static unsigned restarts, network_ready_events;
struct CallControlGuard {};
using esp_peer_signaling_handle_t = void*;
esp_peer_signaling_handle_t g_mqtt_sig_handle = &queued;
enum { MQTT_SIG_EVENT_NETWORK_READY = 1 };
void mqtt_sig_emit_event(int, void*) { ++network_ready_events; }
void mqtt_sig_restart() {
    assert(!Network4g::modem->uart->receiving);
    ++restarts;
    assert(Network4g::GetMqttInstance()->Subscribe("down", 1));
}
void dispatch_mqtt_message(const std::string&, const std::string&) {}
#include "mqtt_connection_dispatch_under_test.inc"
#include "mqtt_connection_handler_under_test.inc"
#include "mqtt_setup_callbacks_under_test.inc"
static void drain() {
    while (!queued.empty()) {
        std::unique_ptr<MqttMessage> message(queued.front()); queued.pop_front();
        mqtt_connection_handler(message->kind == MqttMessage::Kind::Connected);
    }
}

int main() {
    Network4g::initMqtt();
    auto* client = Network4g::GetMqttInstance();
    auto uart = Network4g::modem->uart;
    assert(client && client->IsConnected());
    unsigned before = uart->commands;
    for (unsigned i=0; i<10000; ++i) assert(client->IsConnected());
    assert(before == uart->commands);
    setup_mqtt_callbacks();
    // Malformed/foreign URCs cannot read a missing state or change readiness.
    uart->emit("MQTTURC", {{0,"conn"},{0,{}}});
    uart->emit("MQTTURC", {{0,"conn"},{1,{}},{6,{}}});
    assert(client->IsConnected());
    // Reboot invalidates local state without issuing AT from the receiver.
    uart->emit("MATREADY", {}); assert(!client->IsConnected());
    assert(!client->Publish("telemetry", "latest", 0));
    assert(before == uart->commands); drain(); assert(!g_mqtt_connected);
    // The query command still runs during explicit Connect, and state 1 must
    // mean reconnecting rather than connected. Missing replies cannot reuse
    // a previously signaled event bit.
    uart->query_fails = true;
    assert(!client->Connect("host",1883,"id","user",""));
    uart->query_fails = false; uart->query_missing = true;
    assert(!client->Connect("host",1883,"id","user",""));
    uart->query_missing = false; uart->state = 1;
    assert(client->Connect("host",1883,"id","user",""));
    assert(!queued.empty()); drain(); assert(g_mqtt_connected && restarts == 1);
    // Readers hold the original address while two callers repeatedly request
    // recovery. Real production init is serialized and creates exactly once.
    std::atomic<bool> stop{false};
    std::thread reader([&] {
        while (!stop.load()) {
            assert(Network4g::GetMqttInstance() == client);
            (void)client->IsConnected();
        }
    });
    auto recover = [] { for (unsigned i=0; i<100; ++i) Network4g::initMqtt(); };
    std::thread first(recover), second(recover);
    first.join(); second.join(); stop = true; reader.join();
    drain();
    assert(Network4g::modem->clients_created == 1 && deleted_events == 0);
    assert(client == Network4g::GetMqttInstance() && client->IsConnected());
    assert(network_ready_events > 0);
    // The retained message callback still receives a subsequent incoming call.
    std::string payload;
    client->OnMessage([&](const std::string&, const std::string& body) { payload = body; });
    uart->emit("MQTTURC", {{0,"publish"},{0,{}},{0,{}},{0,"down"},{5,{}},{5,{}},{0,"offer"}});
    assert(payload == "offer");
    puts("PASS: MQTT lifetime across 200 recoveries, concurrent readers, URC-only state, deferred callbacks and next offer");
}
