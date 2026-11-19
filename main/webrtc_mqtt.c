/* DoorBell WebRTC application code

   This example code is in the Public Domain (or CC0 licensed, at your option.)

   Unless required by applicable law or agreed to in writing, this
   software is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
   CONDITIONS OF ANY KIND, either express or implied.
*/

#include <stdio.h>
#include <stdatomic.h>
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
#include "app_config.h"
#include "otaupgrade.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"

static void start_call_timeout(void);
static void stop_call_timeout(void);
static void process_cmd(const char *cmd);
static void process_peer_cmd(const char *cmd);
static void call_control_task(void *param);

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

#define SAME_STR(a, b) (strcmp(a, b) == 0)
#define SEND_CMD(webrtc, cmd) \
    esp_webrtc_send_custom_data(webrtc, ESP_WEBRTC_CUSTOM_DATA_VIA_SIGNALING, (uint8_t *)cmd, strlen(cmd))

typedef struct {
    _Atomic call_state_t state;
    _Atomic bool is_initiator;
    _Atomic bool hangup_by_self;
    bool reconnect_eligible;
    bool has_pending_offer;
    bool was_connected_once;
    bool reconnect_task_running;
    uint8_t reconnect_attempts;
    bool call_timeout_active;
    TickType_t call_deadline;
    TickType_t reconnect_deadline;
    char peer_id[32];
    char last_remote_id[32];
} call_ctx_t;

static esp_webrtc_handle_t webrtc;
static _Atomic bool        monitor_key;
static bool                key_thread_started;
typedef enum {
    CALL_ACTION_COMMAND,
    CALL_ACTION_PEER_COMMAND,
    CALL_ACTION_MQTT_EVENT,
    CALL_ACTION_WEBRTC_EVENT,
} call_action_type_t;

typedef struct {
    call_action_type_t type;
    uint32_t generation;
    uint32_t call_serial;
    int event;
    char text[32];
    char peer_id[32];
} call_action_t;

static QueueHandle_t call_actions;
static SemaphoreHandle_t call_lock;
static _Atomic uint32_t call_generation;
static _Atomic uint32_t call_serial;
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
        size_t len = strnlen(peer_id, sizeof(g_call_ctx.last_remote_id) - 1);
        memmove(g_call_ctx.last_remote_id, peer_id, len);
        g_call_ctx.last_remote_id[len] = '\0';
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

static void cancel_reconnect(void)
{
    g_call_ctx.reconnect_eligible = false;
    g_call_ctx.reconnect_task_running = false;
    g_call_ctx.reconnect_attempts = 0;
    g_call_ctx.was_connected_once = false;
    call_ctx_clear_last_remote_id();
}

static void schedule_auto_reconnect(const char *reason)
{
    call_ctx_update_reconnect_flag();
    if (!g_call_ctx.reconnect_eligible) {
        ESP_LOGI(TAG, "当前不满足自动重拨条件, reason=%s", reason ? reason : "none");
        cancel_reconnect();
        call_ctx_reset_idle(true);
        return;
    }
    if (g_call_ctx.reconnect_task_running) {
        ESP_LOGI(TAG, "自动重拨任务已在运行，忽略重复调度, reason=%s", reason ? reason : "none");
        return;
    }

    g_call_ctx.reconnect_task_running = true;
    g_call_ctx.reconnect_deadline = xTaskGetTickCount() + pdMS_TO_TICKS(AUTO_RECONNECT_DELAY_MS);
    call_ctx_change_state(CALL_STATE_RECONNECTING, reason);
    ESP_LOGI(TAG, "调度自动重拨, reason=%s, next_attempt=%u/%u",
             reason ? reason : "none",
             (unsigned)(g_call_ctx.reconnect_attempts + 1),
             (unsigned)AUTO_RECONNECT_MAX_ATTEMPTS);
}

static int enqueue_action(call_action_t *action)
{
    action->generation = call_generation;
    action->call_serial = call_serial;
    if (!call_actions || xQueueSend(call_actions, action, 0) != pdPASS) {
        ESP_LOGE(TAG, "通话控制队列不可用或已满");
        return -1;
    }
    return 0;
}

static void on_mqtt_signaling_event(mqtt_sig_event_t event, const char *peer_id, void *ctx)
{
    (void)ctx;
    call_action_t action = {.type = CALL_ACTION_MQTT_EVENT, .event = event};
    if (peer_id) {
        snprintf(action.peer_id, sizeof(action.peer_id), "%s", peer_id);
    }
    enqueue_action(&action);
}

static void process_mqtt_event(mqtt_sig_event_t event, const char *peer_id)
{
    if ((event == MQTT_SIG_EVENT_REMOTE_RING || event == MQTT_SIG_EVENT_REMOTE_OFFER) &&
        peer_id && peer_id[0] &&
        (g_call_ctx.state == CALL_STATE_IDLE || g_call_ctx.state == CALL_STATE_RECONNECTING)) {
        call_ctx_set_peer_id(peer_id);
    }
    switch (event) {
        case MQTT_SIG_EVENT_NETWORK_READY:
            // Play locally only after MQTT is online; never interrupt a call.
            if (g_call_ctx.state == CALL_STATE_IDLE && !ota_is_in_progress()) {
                play_tone(DOOR_BELL_TONE_NETWORK_SUCCESS);
            }
            break;
        case MQTT_SIG_EVENT_REMOTE_RING:
        case MQTT_SIG_EVENT_REMOTE_OFFER:
            if (ota_is_in_progress()) {
                mqtt_sig_reject_call();
                break;
            }
            if (g_call_ctx.state == CALL_STATE_IDLE || g_call_ctx.state == CALL_STATE_RECONNECTING) {
                cancel_reconnect();
                call_serial++;
                g_call_ctx.is_initiator = false;
                g_call_ctx.hangup_by_self = false;
                g_call_ctx.reconnect_eligible = false;
                g_call_ctx.has_pending_offer = true;
                call_ctx_change_state(CALL_STATE_INCOMING, "remote_offer");
                play_tone(DOOR_BELL_TONE_INCOMING);
            }
            break;
        case MQTT_SIG_EVENT_REMOTE_ANSWER:
            if (g_call_ctx.state == CALL_STATE_OUTGOING) {
                call_ctx_change_state(CALL_STATE_OUTGOING_CONNECTING, "remote_answer");
            }
            break;
        case MQTT_SIG_EVENT_REMOTE_REJECT:
        case MQTT_SIG_EVENT_REMOTE_CLOSE:
        case MQTT_SIG_EVENT_REMOTE_TIMEOUT:
            stop_call_timeout();
            g_call_ctx.hangup_by_self = false;
            cancel_reconnect();
            call_ctx_reset_idle(true);
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
    if (!data || size < 0 || (size_t)size >= sizeof(((call_action_t *)0)->text)) {
        return -1;
    }
    call_action_t action = {.type = CALL_ACTION_PEER_COMMAND};
    memcpy(action.text, data, size);
    return enqueue_action(&action);
}

static void process_peer_cmd(const char *cmd)
{
    if (!webrtc) {
        return;
    }
    if (SAME_STR(cmd, DOOR_BELL_RING_CMD)) {
        play_tone(DOOR_BELL_TONE_INCOMING);
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
        if (g_call_ctx.state != CALL_STATE_OUTGOING && g_call_ctx.state != CALL_STATE_OUTGOING_CONNECTING) {
            return;
        }
        if (g_call_ctx.state == CALL_STATE_OUTGOING) {
            call_ctx_change_state(CALL_STATE_OUTGOING_CONNECTING, "peer_accepted");
        }
        esp_webrtc_enable_peer_connection(webrtc, true);
    } else if (SAME_STR(cmd, DOOR_BELL_CALL_DENIED_CMD) || SAME_STR(cmd, DOOR_BELL_CALL_REJECTED_CMD)) {
        ESP_LOGI(TAG, "Call rejected by peer");
        stop_call_timeout();
        g_call_ctx.hangup_by_self = false;
        cancel_reconnect();
        call_ctx_reset_idle(true);
        esp_webrtc_enable_peer_connection(webrtc, false);
    }
}

static int webrtc_event_handler(esp_webrtc_event_t *event, void *ctx)
{
    (void)ctx;
    call_action_t action = {.type = CALL_ACTION_WEBRTC_EVENT, .event = event->type};
    return enqueue_action(&action);
}

static void process_webrtc_event(esp_webrtc_event_type_t event)
{
    if (event == ESP_WEBRTC_EVENT_CONNECTING) {
        if (g_call_ctx.state == CALL_STATE_OUTGOING) {
            call_ctx_change_state(CALL_STATE_OUTGOING_CONNECTING, "webrtc_connecting");
        } else if (g_call_ctx.state == CALL_STATE_INCOMING) {
            call_ctx_change_state(CALL_STATE_INCOMING_CONNECTING, "webrtc_connecting");
            start_call_timeout();
        }
    } else if (event == ESP_WEBRTC_EVENT_CONNECTED) {
        if (g_call_ctx.state != CALL_STATE_OUTGOING &&
            g_call_ctx.state != CALL_STATE_OUTGOING_CONNECTING &&
            g_call_ctx.state != CALL_STATE_INCOMING_CONNECTING) {
            return;
        }
        stop_call_timeout();
        g_call_ctx.was_connected_once = true;
        g_call_ctx.reconnect_attempts = 0;
        g_call_ctx.reconnect_task_running = false;
        call_ctx_change_state(CALL_STATE_CONNECTED, "webrtc_connected");
    } else if (event == ESP_WEBRTC_EVENT_DISCONNECTED || event == ESP_WEBRTC_EVENT_CONNECT_FAILED) {
        if (g_call_ctx.state == CALL_STATE_IDLE || g_call_ctx.state == CALL_STATE_RECONNECTING) {
            return;
        }
        stop_call_timeout();
        call_ctx_reset_idle(false);
        if (webrtc) {
            esp_webrtc_enable_peer_connection(webrtc, false);
        }
        schedule_auto_reconnect(event == ESP_WEBRTC_EVENT_DISCONNECTED ? "webrtc_disconnected" : "webrtc_connect_failed");
    }
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
    call_action_t action = {.type = CALL_ACTION_COMMAND, .text = "ring"};
    if (target_id && target_id[0]) {
        if (strlen(target_id) >= sizeof(action.peer_id)) {
            return -1;
        }
        snprintf(action.peer_id, sizeof(action.peer_id), "%s", target_id);
    }
    return enqueue_action(&action);
}

int voice_call_answer(void)
{
    call_action_t action = {.type = CALL_ACTION_COMMAND, .text = "answer"};
    return enqueue_action(&action);
}

int voice_call_reject(void)
{
    call_action_t action = {.type = CALL_ACTION_COMMAND, .text = "reject"};
    return enqueue_action(&action);
}

int voice_call_close(void)
{
    call_action_t action = {.type = CALL_ACTION_COMMAND, .text = "close"};
    return enqueue_action(&action);
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
    if (!cmd || strlen(cmd) >= sizeof(((call_action_t *)0)->text)) {
        return;
    }
    call_action_t action = {.type = CALL_ACTION_COMMAND};
    snprintf(action.text, sizeof(action.text), "%s", cmd);
    enqueue_action(&action);
}

static void begin_outgoing(bool reconnect)
{
    if (!webrtc || ota_is_in_progress()) {
        ESP_LOGE(TAG, "WebRTC 尚未初始化，无法呼出");
        cancel_reconnect();
        call_ctx_reset_idle(true);
        return;
    }
    if (!reconnect) {
        cancel_reconnect();
        call_ctx_set_last_remote_id(g_call_ctx.peer_id);
    }
    call_serial++;
    g_call_ctx.reconnect_task_running = false;
    g_call_ctx.is_initiator = true;
    g_call_ctx.hangup_by_self = false;
    g_call_ctx.reconnect_eligible = false;
    g_call_ctx.has_pending_offer = false;
    call_ctx_change_state(CALL_STATE_OUTGOING, reconnect ? "auto_redial" : "local_ring");
    play_tone(DOOR_BELL_TONE_OUTGOING);
    start_call_timeout();
    SEND_CMD(webrtc, DOOR_BELL_RING_CMD);
    mqtt_sig_send_ring(g_call_ctx.peer_id[0] ? g_call_ctx.peer_id : NULL);
}

static void process_cmd(const char *cmd)
{
    if (SAME_STR(cmd, "ring")) {
        if (g_call_ctx.state != CALL_STATE_IDLE) {
            ESP_LOGW(TAG, "当前状态 %s 不允许再次呼出", webrtc_get_call_state_string());
            return;
        }
        begin_outgoing(false);
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
        start_call_timeout();
        mqtt_sig_answer_call();
    } else if (SAME_STR(cmd, "reject")) {
        if (g_call_ctx.state != CALL_STATE_INCOMING && g_call_ctx.state != CALL_STATE_INCOMING_CONNECTING) {
            ESP_LOGW(TAG, "当前状态 %s 不允许拒绝", webrtc_get_call_state_string());
            return;
        }
        ESP_LOGI(TAG, "User rejecting call");
        g_call_ctx.hangup_by_self = true;
        cancel_reconnect();
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
        cancel_reconnect();
        mqtt_sig_close_call();
        stop_call_timeout();
        call_ctx_reset_idle(true);
        if (webrtc) {
            ESP_LOGI(TAG, "关闭媒体连接，保留 MQTT 信令以便再次通话");
            esp_webrtc_enable_peer_connection(webrtc, false);
        }
    }
}

static void key_monitor_thread(void *arg);

static void start_call_timeout(void)
{
    uint32_t seconds = app_config_get()->call_timeout;
    if (seconds == 0 || seconds > 3600) {
        seconds = 120;
    }
    g_call_ctx.call_timeout_active = true;
    g_call_ctx.call_deadline = xTaskGetTickCount() + pdMS_TO_TICKS(seconds * 1000);
    ESP_LOGI(TAG, "通话连接超时: %lu 秒", (unsigned long)seconds);
}

static void stop_call_timeout(void)
{
    g_call_ctx.call_timeout_active = false;
}

static bool deadline_reached(TickType_t now, TickType_t deadline)
{
    return (int32_t)(now - deadline) >= 0;
}

static void process_call_deadlines(void)
{
    TickType_t now = xTaskGetTickCount();
    if (g_call_ctx.call_timeout_active && deadline_reached(now, g_call_ctx.call_deadline)) {
        stop_call_timeout();
        ESP_LOGI(TAG, "通话连接超时");
        mqtt_sig_send_timeout(g_call_ctx.peer_id[0] ? g_call_ctx.peer_id : NULL);
        call_ctx_reset_idle(false);
        if (webrtc) {
            esp_webrtc_enable_peer_connection(webrtc, false);
        }
        schedule_auto_reconnect("call_timeout");
    }
    if (g_call_ctx.reconnect_task_running &&
        g_call_ctx.state == CALL_STATE_RECONNECTING &&
        deadline_reached(now, g_call_ctx.reconnect_deadline)) {
        g_call_ctx.reconnect_task_running = false;
        call_ctx_update_reconnect_flag();
        if (!g_call_ctx.reconnect_eligible) {
            cancel_reconnect();
            call_ctx_reset_idle(true);
            return;
        }
        g_call_ctx.reconnect_attempts++;
        ESP_LOGI(TAG, "开始第 %u/%u 次自动重拨", g_call_ctx.reconnect_attempts,
                 (unsigned)AUTO_RECONNECT_MAX_ATTEMPTS);
        begin_outgoing(true);
    }
}

static void process_action(const call_action_t *action)
{
    if (action->generation != call_generation) {
        return;
    }
    if ((action->type == CALL_ACTION_WEBRTC_EVENT || action->type == CALL_ACTION_PEER_COMMAND) &&
        action->call_serial != call_serial) {
        return;
    }
    switch (action->type) {
        case CALL_ACTION_COMMAND:
            if (SAME_STR(action->text, "ring") && g_call_ctx.state == CALL_STATE_IDLE && action->peer_id[0]) {
                call_ctx_set_peer_id(action->peer_id);
            }
            process_cmd(action->text);
            break;
        case CALL_ACTION_PEER_COMMAND:
            process_peer_cmd(action->text);
            break;
        case CALL_ACTION_MQTT_EVENT:
            process_mqtt_event((mqtt_sig_event_t)action->event, action->peer_id);
            break;
        case CALL_ACTION_WEBRTC_EVENT:
            process_webrtc_event((esp_webrtc_event_type_t)action->event);
            break;
    }
}

static void call_control_task(void *param)
{
    (void)param;
    for (;;) {
        call_action_t action;
        bool received = xQueueReceive(call_actions, &action, pdMS_TO_TICKS(50)) == pdPASS;
        xSemaphoreTakeRecursive(call_lock, portMAX_DELAY);
        if (received) {
            process_action(&action);
        }
        process_call_deadlines();
        xSemaphoreGiveRecursive(call_lock);
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

    for (;;) {
        media_lib_thread_sleep(50);
        if (!monitor_key) {
            continue;
        }
        int level = gpio_get_level(DOOR_BELL_RING_BUTTON);
        if (level != last_level) {
            last_level = level;
            if (level != init_level) {
                send_cmd("ring");
            }
        }
    }
}

void voice_call_lock(void)
{
    if (call_lock) {
        xSemaphoreTakeRecursive(call_lock, portMAX_DELAY);
    }
}

void voice_call_unlock(void)
{
    if (call_lock) {
        xSemaphoreGiveRecursive(call_lock);
    }
}

static int init_call_control(void)
{
    if (call_actions) {
        return 0;
    }
    call_lock = xSemaphoreCreateRecursiveMutex();
    call_actions = xQueueCreate(24, sizeof(call_action_t));
    if (!call_lock || !call_actions ||
        xTaskCreate(call_control_task, "call_control", 8192, NULL, 10, NULL) != pdPASS) {
        if (call_lock) {
            vSemaphoreDelete(call_lock);
            call_lock = NULL;
        }
        if (call_actions) {
            vQueueDelete(call_actions);
            call_actions = NULL;
        }
        ESP_LOGE(TAG, "无法创建通话控制任务");
        return -1;
    }
    return 0;
}

static int ignore_webrtc_event(esp_webrtc_event_t *event, void *ctx)
{
    (void)event;
    (void)ctx;
    return 0;
}

int start_webrtc(char *url)
{
    if (!url || url[0] == 0) {
        ESP_LOGE(TAG, "Room Url not set yet");
        return -1;
    }
    if (init_call_control() != 0) {
        return -1;
    }
    voice_call_lock();
    monitor_key = false;
    if (webrtc) {
        esp_webrtc_set_event_handler(webrtc, ignore_webrtc_event, NULL);
        esp_webrtc_close(webrtc);
        webrtc = NULL;
    }
    call_generation++;
    call_serial++;
    stop_call_timeout();
    call_ctx_reset_idle(true);
    g_call_ctx.is_initiator = false;
    g_call_ctx.hangup_by_self = false;
    g_call_ctx.reconnect_eligible = false;
    g_call_ctx.was_connected_once = false;
    g_call_ctx.reconnect_attempts = 0;
    g_call_ctx.reconnect_task_running = false;
    call_ctx_clear_last_remote_id();
    mqtt_sig_set_event_handler(on_mqtt_signaling_event, NULL);

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
        mqtt_sig_set_webrtc_handle(NULL);
        voice_call_unlock();
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
        esp_webrtc_close(webrtc);
        webrtc = NULL;
        mqtt_sig_set_webrtc_handle(NULL);
    } else {
        monitor_key = true;
        if (!key_thread_started) {
            media_lib_thread_handle_t key_thread;
            key_thread_started = media_lib_thread_create_from_scheduler(&key_thread, "Key", key_monitor_thread, NULL) == 0;
        }
    }
    voice_call_unlock();
    return ret;
}

void query_webrtc(void)
{
    voice_call_lock();
    if (webrtc) {
        esp_webrtc_query(webrtc);
    }
    voice_call_unlock();
}

int stop_webrtc(void)
{
    voice_call_lock();
    call_generation++;
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
        esp_webrtc_set_event_handler(handle, ignore_webrtc_event, NULL);
        mqtt_sig_set_webrtc_handle(NULL);
        ESP_LOGI(TAG, "Start to close webrtc %p", handle);
        esp_webrtc_close(handle);
    }
    call_ctx_reset_idle(true);
    mqtt_sig_set_event_handler(NULL, NULL);
    voice_call_unlock();
    return 0;
}

//webrtc.cpp
