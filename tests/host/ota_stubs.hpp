#pragma once
#include <atomic>
#include <cassert>
#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <list>
#include <memory>
#include <new>
#include <string>
#include <vector>
#include "mbedtls/md5.h"
#include "otaupgrade.h"
#include "webrtc_mqtt.h"

#define ESP_LOGI(...) ((void)0)
#define ESP_LOGW(...) ((void)0)
#define ESP_LOGE(...) ((void)0)
#define BIT0 1u
#define BIT1 2u
#define BIT2 4u
#define BIT3 8u
#define pdTRUE true
#define pdFALSE false
#define pdPASS 1
#define pdMS_TO_TICKS(ms) (ms)
#define ESP_OK 0
#define ESP_ERR_OTA_VALIDATE_FAILED 1
#define OTA_SIZE_UNKNOWN 0
typedef int esp_err_t;
typedef int esp_ota_handle_t;
typedef void *TaskHandle_t;
typedef void *SemaphoreHandle_t;
typedef unsigned *EventGroupHandle_t;
struct esp_partition_t { const char *label; unsigned long address, size; };
struct esp_app_desc_t { char version[16], project_name[16], date[16], time[16]; };

struct AtArgumentValue {
    enum class Type { String, Int } type;
    std::string string_value;
    int int_value = 0;
    AtArgumentValue(const std::string& value) : type(Type::String), string_value(value) {}
    AtArgumentValue(int value) : type(Type::Int), int_value(value) {}
};
using UrcCallback = std::function<void(const std::string&, const std::vector<AtArgumentValue>&)>;
class AtUart {
public:
    std::list<UrcCallback> callbacks;
    std::list<UrcCallback>::iterator RegisterUrcCallback(UrcCallback cb) {
        callbacks.push_back(cb);
        return std::prev(callbacks.end());
    }
    void UnregisterUrcCallback(std::list<UrcCallback>::iterator it) { callbacks.erase(it); }
    bool SendCommand(const std::string&, int);
    std::string EncodeHex(const std::string& value) { return value; }
    void DecodeHexAppend(std::string& out, const char *hex, size_t len) {
        for (size_t i = 0; i + 1 < len; i += 2) {
            unsigned value;
            if (sscanf(std::string(hex + i, 2).c_str(), "%2x", &value) == 1) out += (char)value;
        }
    }
};
class AtModem {
public:
    std::shared_ptr<AtUart> uart = std::make_shared<AtUart>();
    bool network_ready() { return true; }
    std::shared_ptr<AtUart> GetAtUart() { return uart; }
};
namespace Network4g { AtModem *GetModemInstance(); }

void voice_call_lock(void);
void voice_call_unlock(void);
int xTaskCreate(void (*)(void *), const char *, int, void *, int, TaskHandle_t *);
TaskHandle_t xTaskGetCurrentTaskHandle(void);
void vTaskDelete(TaskHandle_t);
void vTaskDelay(unsigned);
SemaphoreHandle_t xSemaphoreCreateBinary(void);
void vSemaphoreDelete(SemaphoreHandle_t);
EventGroupHandle_t xEventGroupCreate(void);
unsigned xEventGroupSetBits(EventGroupHandle_t, unsigned);
unsigned xEventGroupWaitBits(EventGroupHandle_t, unsigned, bool, bool, unsigned);
void vEventGroupDelete(EventGroupHandle_t);
const esp_partition_t *esp_ota_get_next_update_partition(const void *);
const esp_partition_t *esp_ota_get_running_partition(void);
int esp_ota_get_partition_description(const esp_partition_t *, esp_app_desc_t *);
int esp_ota_begin(const esp_partition_t *, unsigned, esp_ota_handle_t *);
int esp_ota_write(esp_ota_handle_t, const void *, size_t);
int esp_ota_abort(esp_ota_handle_t);
int esp_ota_end(esp_ota_handle_t);
int esp_ota_set_boot_partition(const esp_partition_t *);
int esp_task_wdt_add(TaskHandle_t);
int esp_task_wdt_delete(TaskHandle_t);
const char *esp_err_to_name(int);
void esp_restart(void);
