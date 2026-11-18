package com.youkong.audio_server.dto;

import lombok.Data;

import java.util.List;

/**
 * WebRTC 信令消息 DTO
 */
@Data
public class SignalingMessage {

    /**
     * 信令类型
     */
    private String type;

    /**
     * 目标设备/会话ID
     */
    private String target="web_client_001";

    /**
     * 发送方ID
     */
    private String from;

    /**
     * 时间戳
     */
    private Long timestamp;

    /**
     * SDP 内容 (offer/answer)
     */
    private String sdp;

    /**
     * ICE 候选信息
     */
    private String candidate;

    /**
     * ICE 服务器列表
     */
    private List<IceServer> iceServers;

    /**
     * 自定义数据
     */
    private Object data;

    private String url;

    private String md5;

    private Integer version;

    /**
     * ICE 服务器配置
     */
    @Data
    public static class IceServer {
        private List<String> urls;
        private String username;
        private String credential;
    }

    /**
     * Adapt browser fields to the ESP32 protocol without changing its wire format.
     * Keep both representations so the original and updated test pages work.
     */
    public void normalizeMediaFields() {
        if ("offer".equals(type) || "answer".equals(type)) {
            String value = sdp != null && !sdp.isEmpty() ? sdp
                    : data instanceof String ? (String) data : null;
            if (value != null) {
                sdp = value;
                data = value;
            }
        } else if ("candidate".equals(type)) {
            String value = candidate != null && !candidate.isEmpty() ? candidate
                    : data instanceof String ? (String) data : null;
            if (value != null) {
                candidate = value;
                data = value;
            }
        }
    }

    /**
     * 验证消息是否合法
     */
    public boolean isValid() {
        if (type == null || type.isEmpty()) {
            return false;
        }
        // register 消息只需要 from 字段（WebSocket 会话注册自己的 ID）
        if ("register".equals(type) || "register_response".equals(type)) {
            return from != null && !from.isEmpty() && timestamp != null;
        }
        // ice_request 不需要 target 字段
        if ("ice_request".equals(type)) {
            return timestamp != null;
        }
        // customized 信令 target 字段可选（用于广播场景）
        if ("customized".equals(type)) {
            return timestamp != null;
        }
        // version_report 需要 device_id 和 version
        if ("version_report".equals(type)) {
            return version != null;
        }
        // ota 消息需要 target, url, timestamp
        if ("ota".equals(type)) {
            return target != null && !target.isEmpty() && timestamp != null;
        }
        // version_query 需要 target 和 timestamp
        if ("version_query".equals(type)) {
            return target != null && !target.isEmpty() && timestamp != null;
        }
        if (("offer".equals(type) || "answer".equals(type)) &&
                (sdp == null || sdp.isEmpty())) {
            return false;
        }
        if ("candidate".equals(type) && (candidate == null || candidate.isEmpty())) {
            return false;
        }
        // 其他消息需要 target 和 timestamp
        return target != null && !target.isEmpty() && timestamp != null;
    }

    /**
     * 获取响应主题
     */
    public String getDownTopic(String project) {
        return String.format("/voice/%s/%s/down", project, target);
    }
}
