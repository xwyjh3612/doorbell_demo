/* DoorBell WebRTC application code

   This example code is in the Public Domain (or CC0 licensed, at your option.)

   Unless required by applicable law or agreed to in writing, this
   software is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
   CONDITIONS OF ANY KIND, either express or implied.
*/

#include <string.h>
#include "esp_webrtc.h"
#include "media_lib_os.h"
#include "driver/gpio.h"
#include "common.h"
#include "esp_log.h"
#include "esp_webrtc_defaults.h"
#include "esp_peer_default.h"
#include "mqtt_signaling.h"
#include "webrtc_mqtt.h"
#include "door_bell_audio.h"
#include "freertos/FreeRTOS.h"
#include "freertos/timers.h"

static void start_call_timeout(void);
static void stop_call_timeout(void);

#define TAG "DOOR_BELL"
#define AUTO_RECONNECT_MAX_ATTEMPTS 3
#define AUTO_RECONNECT_DELAY_MS 1500

// Customized commands
#define DOOR_BELL_OPEN_DOOR_CMD     "OPEN_DOOR"
#define DOOR_BELL_DOOR_OPENED_CMD   "DOOR_OPENED"
#define DOOR_BELL_RING_CMD          "RING"
#define DOOR_BELL_CALL_ACCEPTED_CMD "ACCEPT_CALL"
#define DOOR_BELL_CALL_DENIED_CMD   "DENY_CALL"
#define DOOR_BELL_CALL_REJECTED_CMD "REJECT_CALL"

#define SAME_STR(a, b) (strncmp(a, b, sizeof(b) - 1) == 0)
#define SEND_CMD(webrtc, cmd) \
    esp_webrtc_send_custom_data(webrtc, ESP_WEBRTC_CUSTOM_DATA_VIA_SIGNALING, (uint8_t *)cmd, strlen(cmd))

typedef struct {
    call_state_t state;
    bool is_initiator;
    bool hangup_by_self;
    bool reconnect_eligible;
    bool has_pending_offer;
    bool was_connected_once;
    bool reconnect_task_running;
    uint8_t reconnect_attempts;
    char peer_id[32];
    char last_remote_id[32];
} call_ctx_t;

static esp_webrtc_handle_t webrtc;
static bool                monitor_key;
static TimerHandle_t       call_timeout_timer;
static TaskHandle_t        call_timeout_handle = NULL;
static call_ctx_t          g_call_ctx = {
    .state = CALL_STATE_IDLE,
    .is_initiator = false,
    .hangup_by_self = false,
    .reconnect_eligible = false,
    .has_pending_offer = false,
    .was_connected_once = false,
    .reconnect_task_running = false,
    .reconnect_attempts = 0,
    .peer_id = {0},
    .last_remote_id = {0},
};

extern const uint8_t ring_music_start[] asm("_binary_ring_aac_start");
extern const uint8_t ring_music_end[] asm("_binary_ring_aac_end");
extern const uint8_t open_music_start[] asm("_binary_open_aac_start");
extern const uint8_t open_music_end[] asm("_binary_open_aac_end");
extern const uint8_t join_music_start[] asm("_binary_join_aac_start");
extern const uint8_t join_music_end[] asm("_binary_join_aac_end");

static const char *call_state_to_string(call_state_t state)
{
    switch (state) {
        case CALL_STATE_IDLE:
            return "idle"; //空闲状态，其他状态都不允许系统升级
        case CALL_STATE_OUTGOING:
            return "outgoing";
        case CALL_STATE_OUTGOING_CONNECTING:
            return "outgoing_connecting";
        case CALL_STATE_INCOMING:
            return "incoming";
        case CALL_STATE_INCOMING_CONNECTING:
            return "incoming_connecting";
        case CALL_STATE_CONNECTED:
            return "connected";
        case CALL_STATE_RECONNECTING:
            return "reconnecting";
        default:
            return "unknown";
    }
}

static void call_ctx_set_peer_id(const char *peer_id)
{
    if (peer_id && peer_id[0]) {
        strncpy(g_call_ctx.peer_id, peer_id, sizeof(g_call_ctx.peer_id) - 1);
        g_call_ctx.peer_id[sizeof(g_call_ctx.peer_id) - 1] = '\0';
    }
}

static void call_ctx_set_last_remote_id(const char *peer_id)
{
    if (peer_id && peer_id[0]) {
        strncpy(g_call_ctx.last_remote_id, peer_id, sizeof(g_call_ctx.last_remote_id) - 1);
        g_call_ctx.last_remote_id[sizeof(g_call_ctx.last_remote_id) - 1] = '\0';
    }
}

static void call_ctx_clear_last_remote_id(void)
{
    g_call_ctx.last_remote_id[0] = '\0';
}

static void call_ctx_reset_idle(bool clear_peer)
{
    g_call_ctx.state = CALL_STATE_IDLE;
    g_call_ctx.has_pending_offer = false;
    g_call_ctx.reconnect_eligible = false;
    g_call_ctx.reconnect_task_running = false;
    if (clear_peer) {
        g_call_ctx.peer_id[0] = '\0';
    }
    stop_music();
}

static void call_ctx_update_reconnect_flag(void)
{
    /* 中文注释：仅在已经接通过一次、当前是主叫且不是主动挂断时，才允许自动重拨。 */
    g_call_ctx.reconnect_eligible = (g_call_ctx.is_initiator &&
                                     !g_call_ctx.hangup_by_self &&
                                     g_call_ctx.was_connected_once &&
                                     g_call_ctx.last_remote_id[0] != '\0' &&
                                     g_call_ctx.reconnect_attempts < AUTO_RECONNECT_MAX_ATTEMPTS);
}

static void call_ctx_change_state(call_state_t new_state, const char *reason)
{
    if (g_call_ctx.state == new_state) {
        ESP_LOGI(TAG, "通话状态保持: %s, reason=%s", call_state_to_string(new_state), reason ? reason : "none");
        return;
    }
    ESP_LOGI(TAG, "通话状态切换: %s -> %s, reason=%s",
             call_state_to_string(g_call_ctx.state),
             call_state_to_string(new_state),
             reason ? reason : "none");
    g_call_ctx.state = new_state;
    if (new_state == CALL_STATE_IDLE ||
        new_state == CALL_STATE_OUTGOING_CONNECTING ||
        new_state == CALL_STATE_INCOMING_CONNECTING ||
        new_state == CALL_STATE_CONNECTED) {
        stop_music();
    }
}

static void auto_reconnect_task(void *param)
{
    (void)param;
    ESP_LOGI(TAG, "自动重拨任务启动，等待 %d ms", AUTO_RECONNECT_DELAY_MS);
    vTaskDelay(pdMS_TO_TICKS(AUTO_RECONNECT_DELAY_MS));

    g_call_ctx.reconnect_task_running = false;
    call_ctx_update_reconnect_flag();
    if (!g_call_ctx.reconnect_eligible) {
        ESP_LOGI(TAG, "自动重拨条件不满足，取消执行");
        vTaskDelete(NULL);
        return;
    }
    if (g_call_ctx.state != CALL_STATE_IDLE) {
        ESP_LOGI(TAG, "当前状态 %s 非空闲，放弃自动重拨", webrtc_get_call_state_string());
        vTaskDelete(NULL);
        return;
    }

    g_call_ctx.reconnect_attempts++;
    ESP_LOGI(TAG, "开始第 %u/%u 次自动重拨，对端=%s",
             g_call_ctx.reconnect_attempts,
             (unsigned)AUTO_RECONNECT_MAX_ATTEMPTS,
             g_call_ctx.last_remote_id);
    voice_call_offer(g_call_ctx.last_remote_id);
    vTaskDelete(NULL);
}

static void schedule_auto_reconnect(const char *reason)
{
    call_ctx_update_reconnect_flag();
    if (!g_call_ctx.reconnect_eligible) {
        ESP_LOGI(TAG, "当前不满足自动重拨条件, reason=%s", reason ? reason : "none");
        return;
    }
    if (g_call_ctx.reconnect_task_running) {
        ESP_LOGI(TAG, "自动重拨任务已在运行，忽略重复调度, reason=%s", reason ? reason : "none");
        return;
    }

    g_call_ctx.reconnect_task_running = true;
    ESP_LOGI(TAG, "调度自动重拨, reason=%s, next_attempt=%u/%u",
             reason ? reason : "none",
             (unsigned)(g_call_ctx.reconnect_attempts + 1),
             (unsigned)AUTO_RECONNECT_MAX_ATTEMPTS);
    xTaskCreate(auto_reconnect_task, "auto_reconnect", 4096, NULL, 5, NULL);
}


static void on_mqtt_signaling_event(mqtt_sig_event_t event, const char *peer_id, void *ctx)
{
    (void)ctx;
    if (peer_id && peer_id[0]) {
        call_ctx_set_peer_id(peer_id);
        call_ctx_set_last_remote_id(peer_id);
    }
    switch (event) {
        case MQTT_SIG_EVENT_REMOTE_RING:
        case MQTT_SIG_EVENT_REMOTE_OFFER:
            if (g_call_ctx.state == CALL_STATE_IDLE) {
                g_call_ctx.is_initiator = false;
                g_call_ctx.hangup_by_self = false;
                g_call_ctx.reconnect_eligible = false;
                g_call_ctx.has_pending_offer = true;
                call_ctx_change_state(CALL_STATE_INCOMING, "remote_offer");
                play_tone(DOOR_BELL_TONE_RING);
            }
            break;
        case MQTT_SIG_EVENT_REMOTE_ANSWER:
            if (g_call_ctx.state == CALL_STATE_OUTGOING) {
                stop_call_timeout();
                call_ctx_change_state(CALL_STATE_OUTGOING_CONNECTING, "remote_answer");
            }
            break;
        case MQTT_SIG_EVENT_REMOTE_REJECT:
            stop_call_timeout();
            g_call_ctx.hangup_by_self = false;
            g_call_ctx.reconnect_eligible = false;
            g_call_ctx.reconnect_attempts = 0;
            g_call_ctx.was_connected_once = false;
            g_call_ctx.reconnect_task_running = false;
            call_ctx_clear_last_remote_id();
            if (webrtc) {
                esp_webrtc_enable_peer_connection(webrtc, false);
            }
            call_ctx_reset_idle(true);
            break;
        case MQTT_SIG_EVENT_REMOTE_CLOSE:
        case MQTT_SIG_EVENT_REMOTE_TIMEOUT:
            stop_call_timeout();
            g_call_ctx.hangup_by_self = false;
            if (webrtc) {
                esp_webrtc_enable_peer_connection(webrtc, false);
            }
            break;
        default:
            break;
    }
}

static int door_bell_on_cmd(esp_webrtc_custom_data_via_t via, uint8_t *data, int size, void *ctx)
{
    (void)via;
    (void)ctx;
    if (size == 0 || webrtc == NULL) {
        return 0;
    }
    ESP_LOGI(TAG, "Receive command %.*s", size, (char *)data);
    const char *cmd = (const char *)data;
    if (SAME_STR(cmd, DOOR_BELL_RING_CMD)) {
        play_tone(DOOR_BELL_TONE_RING);
        if (g_call_ctx.state == CALL_STATE_IDLE) {
            g_call_ctx.is_initiator = false;
            g_call_ctx.hangup_by_self = false;
            g_call_ctx.reconnect_eligible = false;
            call_ctx_change_state(CALL_STATE_INCOMING, "peer_ring_cmd");
        }
        if (g_call_ctx.state == CALL_STATE_INCOMING) {
            esp_webrtc_enable_peer_connection(webrtc, true);
        }
    } else if (SAME_STR(cmd, DOOR_BELL_OPEN_DOOR_CMD)) {
        // 中文注释：收到开门命令后回复已开门，并在未接通时播放提示音。
        SEND_CMD(webrtc, DOOR_BELL_DOOR_OPENED_CMD);
        if (g_call_ctx.state != CALL_STATE_CONNECTED) {
            play_tone(DOOR_BELL_TONE_OPEN_DOOR);
        }
    } else if (SAME_STR(cmd, DOOR_BELL_CALL_ACCEPTED_CMD)) {
        stop_call_timeout();
        if (g_call_ctx.state == CALL_STATE_OUTGOING) {
            call_ctx_change_state(CALL_STATE_OUTGOING_CONNECTING, "peer_accepted");
        }
        esp_webrtc_enable_peer_connection(webrtc, true);
    } else if (SAME_STR(cmd, DOOR_BELL_CALL_DENIED_CMD) || SAME_STR(cmd, DOOR_BELL_CALL_REJECTED_CMD)) {
        ESP_LOGI(TAG, "Call rejected by peer");
        stop_call_timeout();
        g_call_ctx.hangup_by_self = false;
        g_call_ctx.reconnect_eligible = false;
        g_call_ctx.reconnect_attempts = 0;
        g_call_ctx.was_connected_once = false;
        g_call_ctx.reconnect_task_running = false;
        call_ctx_clear_last_remote_id();
        esp_webrtc_enable_peer_connection(webrtc, false);
        call_ctx_reset_idle(true);
    }
    return 0;
}

static int webrtc_event_handler(esp_webrtc_event_t *event, void *ctx)
{
    (void)ctx;
    if (event->type == ESP_WEBRTC_EVENT_CONNECTING) {
        if (g_call_ctx.state == CALL_STATE_OUTGOING) {
            call_ctx_change_state(CALL_STATE_OUTGOING_CONNECTING, "webrtc_connecting");
        } else if (g_call_ctx.state == CALL_STATE_INCOMING) {
            call_ctx_change_state(CALL_STATE_INCOMING_CONNECTING, "webrtc_connecting");
        }
    } else if (event->type == ESP_WEBRTC_EVENT_CONNECTED) {
        stop_call_timeout();
        g_call_ctx.was_connected_once = true;
        g_call_ctx.reconnect_attempts = 0;
        g_call_ctx.reconnect_task_running = false;
        call_ctx_change_state(CALL_STATE_CONNECTED, "webrtc_connected");
    } else if (event->type == ESP_WEBRTC_EVENT_DISCONNECTED || event->type == ESP_WEBRTC_EVENT_CONNECT_FAILED) {
        stop_call_timeout();
        if (g_call_ctx.state == CALL_STATE_CONNECTED) {
            call_ctx_update_reconnect_flag();
            if (webrtc) {
                esp_webrtc_enable_peer_connection(webrtc, false);
            }
            call_ctx_reset_idle(false);
            schedule_auto_reconnect(event->type == ESP_WEBRTC_EVENT_DISCONNECTED ? "webrtc_disconnected" : "webrtc_connect_failed");
        } else {
            g_call_ctx.reconnect_eligible = false;
            g_call_ctx.reconnect_attempts = 0;
            g_call_ctx.was_connected_once = false;
            call_ctx_reset_idle(true);
        }
    }
    return 0;
}

call_state_t webrtc_get_call_state(void)
{
    return g_call_ctx.state;
}

const char* webrtc_get_call_state_string(void)
{
    return call_state_to_string(g_call_ctx.state);
}

bool webrtc_is_initiator(void)
{
    return g_call_ctx.is_initiator;
}

bool webrtc_was_hangup_by_self(void)
{
    return g_call_ctx.hangup_by_self;
}

const char* webrtc_get_peer_id(void)
{
    return g_call_ctx.peer_id;
}

int voice_call_offer(const char* target_id)
{
    if (target_id && target_id[0]) {
        call_ctx_set_peer_id(target_id);
        call_ctx_set_last_remote_id(target_id);
    }
    send_cmd("ring");
    return 0;
}

int voice_call_answer(void)
{
    send_cmd("answer");
    return 0;
}

int voice_call_reject(void)
{
    send_cmd("reject");
    return 0;
}

int voice_call_close(void)
{
    send_cmd("close");
    return 0;
}

const char* voice_call_get_state_name(void)
{
    return webrtc_get_call_state_string();
}

const char* voice_call_get_peer_id(void)
{
    return webrtc_get_peer_id();
}

void send_cmd(const char *cmd)
{
    if (SAME_STR(cmd, "ring")) {
        if (g_call_ctx.state != CALL_STATE_IDLE) {
            ESP_LOGW(TAG, "当前状态 %s 不允许再次呼出", webrtc_get_call_state_string());
            return;
        }
        g_call_ctx.reconnect_task_running = false;
        if (webrtc) {
            SEND_CMD(webrtc, DOOR_BELL_RING_CMD);
        }
        g_call_ctx.is_initiator = true;
        g_call_ctx.hangup_by_self = false;
        g_call_ctx.reconnect_eligible = false;
        g_call_ctx.has_pending_offer = false;
        call_ctx_change_state(CALL_STATE_OUTGOING, "local_ring");
        play_tone(DOOR_BELL_TONE_RING);
        mqtt_sig_send_ring(g_call_ctx.peer_id[0] ? g_call_ctx.peer_id : NULL);
        start_call_timeout();
    } else if (SAME_STR(cmd, "answer")) {
        if (g_call_ctx.state != CALL_STATE_INCOMING) {
            ESP_LOGW(TAG, "当前状态 %s 不允许接听", webrtc_get_call_state_string());
            return;
        }
        ESP_LOGI(TAG, "User answering call");
        g_call_ctx.is_initiator = false;
        g_call_ctx.hangup_by_self = false;
        g_call_ctx.has_pending_offer = false;
        call_ctx_change_state(CALL_STATE_INCOMING_CONNECTING, "local_answer");
        mqtt_sig_answer_call();
        stop_call_timeout();
    } else if (SAME_STR(cmd, "reject")) {
        if (g_call_ctx.state != CALL_STATE_INCOMING && g_call_ctx.state != CALL_STATE_INCOMING_CONNECTING) {
            ESP_LOGW(TAG, "当前状态 %s 不允许拒绝", webrtc_get_call_state_string());
            return;
        }
        ESP_LOGI(TAG, "User rejecting call");
        g_call_ctx.hangup_by_self = true;
        g_call_ctx.reconnect_eligible = false;
        g_call_ctx.reconnect_attempts = 0;
        g_call_ctx.was_connected_once = false;
        g_call_ctx.reconnect_task_running = false;
        call_ctx_clear_last_remote_id();
        mqtt_sig_reject_call();
        stop_call_timeout();
        call_ctx_reset_idle(true);
    } else if (SAME_STR(cmd, "close")) {
        if (g_call_ctx.state == CALL_STATE_IDLE) {
            ESP_LOGI(TAG, "当前已经空闲，忽略挂断请求");
            return;
        }
        ESP_LOGI(TAG, "User closing call");
        g_call_ctx.hangup_by_self = true;
        g_call_ctx.reconnect_eligible = false;
        g_call_ctx.reconnect_attempts = 0;
        g_call_ctx.was_connected_once = false;
        g_call_ctx.reconnect_task_running = false;
        call_ctx_clear_last_remote_id();
        mqtt_sig_close_call();
        stop_call_timeout();
        if (webrtc) {
            ESP_LOGI(TAG, "Closing webrtc connection");
            esp_webrtc_close(webrtc);
            webrtc = NULL;
        }
        call_ctx_reset_idle(true);
    }
}

static void key_monitor_thread(void *arg);

static void call_timeout_task(void *param)
{
    (void)param;
    call_timeout_handle = xTaskGetCurrentTaskHandle();
    ESP_LOGI(TAG, "Call timeout task started, waiting 10 seconds...");
    vTaskDelay(pdMS_TO_TICKS(10000));

    if (g_call_ctx.state == CALL_STATE_OUTGOING || g_call_ctx.state == CALL_STATE_OUTGOING_CONNECTING) {
        ESP_LOGI(TAG, "Call timeout, sending timeout to peer");
        mqtt_sig_send_timeout(g_call_ctx.peer_id[0] ? g_call_ctx.peer_id : NULL);
        g_call_ctx.hangup_by_self = false;
        g_call_ctx.reconnect_eligible = false;
        g_call_ctx.reconnect_attempts = 0;
        g_call_ctx.was_connected_once = false;
        g_call_ctx.reconnect_task_running = false;
        call_ctx_clear_last_remote_id();
        call_ctx_reset_idle(true);
    }
    call_timeout_handle = NULL;
    vTaskDelete(NULL);
}

static void start_call_timeout(void)
{
    if (call_timeout_handle != NULL) {
        ESP_LOGI(TAG, "Deleting existing timeout task");
        vTaskDelete(call_timeout_handle);
        call_timeout_handle = NULL;
    }
    xTaskCreate(call_timeout_task, "call_timeout", 4096, NULL, 5, NULL);
    ESP_LOGI(TAG, "Call timeout task created (10 seconds)");
}

static void stop_call_timeout(void)
{
    if (call_timeout_handle != NULL) {
        ESP_LOGI(TAG, "Stopping call timeout, deleting task");
        vTaskDelete(call_timeout_handle);
        call_timeout_handle = NULL;
    }
}

static void key_monitor_thread(void *arg)
{
    (void)arg;
    gpio_config_t io_conf;
    memset(&io_conf, 0, sizeof(io_conf));
    io_conf.mode = GPIO_MODE_INPUT;
    io_conf.pin_bit_mask = BIT64(DOOR_BELL_RING_BUTTON);
    io_conf.pull_down_en = 1;
    esp_err_t ret = 0;
    ret |= gpio_config(&io_conf);
    (void)ret;

    media_lib_thread_sleep(50);
    int last_level = gpio_get_level(DOOR_BELL_RING_BUTTON);
    int init_level = last_level;

    while (monitor_key) {
        media_lib_thread_sleep(50);
        int level = gpio_get_level(DOOR_BELL_RING_BUTTON);
        if (level != last_level) {
            last_level = level;
            if (level != init_level) {
                send_cmd("ring");
            }
        }
    }
    media_lib_thread_destroy(NULL);
}

int start_webrtc(char *url)
{
    if (url[0] == 0) {
        ESP_LOGE(TAG, "Room Url not set yet");
        return -1;
    }
    if (webrtc) {
        esp_webrtc_close(webrtc);
        webrtc = NULL;
    }
    monitor_key = true;
    call_ctx_reset_idle(true);
    g_call_ctx.is_initiator = false;
    g_call_ctx.hangup_by_self = false;
    g_call_ctx.reconnect_eligible = false;
    g_call_ctx.was_connected_once = false;
    g_call_ctx.reconnect_attempts = 0;
    g_call_ctx.reconnect_task_running = false;
    call_ctx_clear_last_remote_id();
    mqtt_sig_set_event_handler(on_mqtt_signaling_event, NULL);

    media_lib_thread_handle_t key_thread;
    media_lib_thread_create_from_scheduler(&key_thread, "Key", key_monitor_thread, NULL);

    esp_peer_default_cfg_t peer_cfg = {
        .agent_recv_timeout = 500,
    };
    esp_webrtc_cfg_t cfg = {
        .peer_cfg = {
            .audio_info = {
                .codec = ESP_PEER_AUDIO_CODEC_OPUS,
                .sample_rate = 16000,
                .channel = 1,
            },
            .video_info = {
                .codec = ESP_PEER_VIDEO_CODEC_NONE,
            },
            .audio_dir = ESP_PEER_MEDIA_DIR_SEND_RECV,
            .video_dir = ESP_PEER_MEDIA_DIR_NONE,
            .on_custom_data = door_bell_on_cmd,
            .enable_data_channel = DATA_CHANNEL_ENABLED,
            .no_auto_reconnect = true,
            .extra_cfg = &peer_cfg,
            .extra_size = sizeof(peer_cfg),
        },
        .signaling_cfg = {
            .signal_url = url,
        },
        .peer_impl = esp_peer_get_default_impl(),
        .signaling_impl = esp_signaling_get_mqtt_impl(),
    };
    int ret = esp_webrtc_open(&cfg, &webrtc);
    if (ret != 0) {
        ESP_LOGE(TAG, "Fail to open webrtc");
        return ret;
    }

    mqtt_sig_set_webrtc_handle(webrtc);
    esp_webrtc_media_provider_t media_provider = {};
    media_sys_get_provider(&media_provider);
    esp_webrtc_set_media_provider(webrtc, &media_provider);
    esp_webrtc_set_event_handler(webrtc, webrtc_event_handler, NULL);
    esp_webrtc_enable_peer_connection(webrtc, false);

    ret = esp_webrtc_start(webrtc);
    if (ret != 0) {
        ESP_LOGE(TAG, "Fail to start webrtc");
    } else {
        play_tone(DOOR_BELL_TONE_JOIN_SUCCESS);
    }
    return ret;
}

void query_webrtc(void)
{
    if (webrtc) {
        esp_webrtc_query(webrtc);
    }
}

int stop_webrtc(void)
{
    monitor_key = false;
    stop_call_timeout();
    g_call_ctx.hangup_by_self = true;
    g_call_ctx.reconnect_eligible = false;
    g_call_ctx.reconnect_attempts = 0;
    g_call_ctx.was_connected_once = false;
    g_call_ctx.reconnect_task_running = false;
    call_ctx_clear_last_remote_id();
    if (webrtc) {
        esp_webrtc_handle_t handle = webrtc;
        webrtc = NULL;
        ESP_LOGI(TAG, "Start to close webrtc %p", handle);
        esp_webrtc_close(handle);
    }
    call_ctx_reset_idle(true);
    return 0;
}

//webrtc.cpp
