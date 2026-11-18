#pragma once
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdatomic.h>
#include "webrtc_mqtt.h"
#include "app_config.h"
#include "mqtt_signaling.h"
#include "otaupgrade.h"
#include "door_bell_audio.h"

typedef uint32_t TickType_t;
typedef void *QueueHandle_t;
typedef void *SemaphoreHandle_t;
typedef void *TaskHandle_t;
typedef void *media_lib_thread_handle_t;
typedef int esp_err_t;
#define pdPASS 1
#define portMAX_DELAY UINT32_MAX
#define pdMS_TO_TICKS(ms) ((TickType_t)(ms))
#define GPIO_MODE_INPUT 1
#define BIT64(pin) (UINT64_C(1) << (pin))
#define DOOR_BELL_RING_BUTTON 0
#define DATA_CHANNEL_ENABLED false
#define ESP_LOGI(...) ((void)0)
#define ESP_LOGW(...) ((void)0)
#define ESP_LOGE(...) ((void)0)

typedef struct { int mode; uint64_t pin_bit_mask; int pull_down_en; } gpio_config_t;
typedef void *esp_webrtc_handle_t;
typedef int esp_webrtc_custom_data_via_t;
typedef enum {
    ESP_WEBRTC_EVENT_CONNECTING,
    ESP_WEBRTC_EVENT_CONNECTED,
    ESP_WEBRTC_EVENT_DISCONNECTED,
    ESP_WEBRTC_EVENT_CONNECT_FAILED,
} esp_webrtc_event_type_t;
typedef struct { esp_webrtc_event_type_t type; } esp_webrtc_event_t;
typedef int (*event_handler_t)(esp_webrtc_event_t *, void *);
typedef struct { int agent_recv_timeout; } esp_peer_default_cfg_t;
typedef struct { int unused; } esp_webrtc_media_provider_t;
#define ESP_PEER_AUDIO_CODEC_OPUS 1
#define ESP_PEER_VIDEO_CODEC_NONE 0
#define ESP_PEER_MEDIA_DIR_SEND_RECV 1
#define ESP_PEER_MEDIA_DIR_NONE 0
#define ESP_WEBRTC_CUSTOM_DATA_VIA_SIGNALING 0
typedef struct {
    struct {
        struct { int codec; int sample_rate; int channel; } audio_info;
        struct { int codec; } video_info;
        int audio_dir;
        int video_dir;
        int (*on_custom_data)(esp_webrtc_custom_data_via_t, uint8_t *, int, void *);
        bool enable_data_channel;
        bool no_auto_reconnect;
        void *extra_cfg;
        size_t extra_size;
    } peer_cfg;
    struct { char *signal_url; } signaling_cfg;
    void *peer_impl;
    const esp_peer_signaling_impl_t *signaling_impl;
} esp_webrtc_cfg_t;

TickType_t xTaskGetTickCount(void);
int xTaskCreate(void (*task)(void *), const char *, int, void *, int, TaskHandle_t *);
QueueHandle_t xQueueCreate(unsigned, size_t);
int xQueueSend(QueueHandle_t, const void *, TickType_t);
int xQueueReceive(QueueHandle_t, void *, TickType_t);
void vQueueDelete(QueueHandle_t);
SemaphoreHandle_t xSemaphoreCreateRecursiveMutex(void);
int xSemaphoreTakeRecursive(SemaphoreHandle_t, TickType_t);
int xSemaphoreGiveRecursive(SemaphoreHandle_t);
void vSemaphoreDelete(SemaphoreHandle_t);
int gpio_config(const gpio_config_t *);
int gpio_get_level(int);
void media_lib_thread_sleep(int);
int media_lib_thread_create_from_scheduler(media_lib_thread_handle_t *, const char *, void (*)(void *), void *);
int esp_webrtc_send_custom_data(esp_webrtc_handle_t, int, uint8_t *, size_t);
int esp_webrtc_enable_peer_connection(esp_webrtc_handle_t, bool);
int esp_webrtc_open(const esp_webrtc_cfg_t *, esp_webrtc_handle_t *);
int esp_webrtc_close(esp_webrtc_handle_t);
int esp_webrtc_start(esp_webrtc_handle_t);
int esp_webrtc_query(esp_webrtc_handle_t);
int esp_webrtc_set_media_provider(esp_webrtc_handle_t, esp_webrtc_media_provider_t *);
int esp_webrtc_set_event_handler(esp_webrtc_handle_t, event_handler_t, void *);
void *esp_peer_get_default_impl(void);
int media_sys_get_provider(esp_webrtc_media_provider_t *);
int stop_music(void);
