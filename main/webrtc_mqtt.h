#ifndef WEBRTC_MQTT_H
#define WEBRTC_MQTT_H

#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    CALL_STATE_IDLE = 0,           // 空闲，无通话
    CALL_STATE_OUTGOING = 1,       // 呼出中，等待对方应答
    CALL_STATE_OUTGOING_CONNECTING = 2, // 呼出连接中，对方已接听
    CALL_STATE_INCOMING = 3,       // 呼入中，等待接听/拒绝
    CALL_STATE_INCOMING_CONNECTING = 4, // 呼入连接中，已接听
    CALL_STATE_CONNECTED = 5,      // 正在通话
    CALL_STATE_RECONNECTING = 6,   // 重连中（未来实现重连策略）
} call_state_t;

call_state_t webrtc_get_call_state(void);
const char* webrtc_get_call_state_string(void);
bool webrtc_is_initiator(void);
bool webrtc_was_hangup_by_self(void);
const char* webrtc_get_peer_id(void);

void send_cmd(const char *cmd);

#ifdef __cplusplus
}
#endif

#endif // WEBRTC_MQTT_H
