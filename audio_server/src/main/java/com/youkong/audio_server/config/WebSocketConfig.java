package com.youkong.audio_server.config;

import com.youkong.audio_server.handler.SignalingWebSocketHandler;
import com.youkong.audio_server.service.DeviceTelemetryService;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

import javax.annotation.Resource;

/**
 * WebSocket 配置类
 */
@Configuration
@EnableWebSocket
public class WebSocketConfig implements WebSocketConfigurer {

    @Resource
    private SignalingWebSocketHandler signalingWebSocketHandler;
    @Resource
    private DeviceTelemetryService telemetryService;

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(signalingWebSocketHandler, "/signaling")
                .setAllowedOrigins("*");
        registry.addHandler(telemetryService, "/telemetry").setAllowedOrigins("*");
    }
}
