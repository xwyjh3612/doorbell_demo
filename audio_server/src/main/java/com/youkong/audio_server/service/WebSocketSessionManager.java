package com.youkong.audio_server.service;

import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;

import java.io.IOException;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

/**
 * WebSocket 会话管理器
 */
@Slf4j
@Service
public class WebSocketSessionManager {

    /**
     * 会话映射表: sessionId -> WebSocketSession
     */
    private final Map<String, WebSocketSession> sessions = new ConcurrentHashMap<>();

    private static final class Phone {
        final String account, device, name, slot;
        Phone(String account,String device,String name,String slot){
            this.account=account;this.device=device;this.name=name;this.slot=slot;
        }
    }
    private final Map<String,Phone> phones = new ConcurrentHashMap<>();
    private final Map<String,String> slots = new ConcurrentHashMap<>();
    @org.springframework.beans.factory.annotation.Value("${signaling.open-demo-device:189833342344184}")
    private String openDemoDevice;
    private final ScheduledExecutorService heartbeatExecutor = Executors.newSingleThreadScheduledExecutor();

    public WebSocketSessionManager() {
        // 启动定时清理任务
        heartbeatExecutor.scheduleAtFixedRate(this::cleanupInactiveSessions, 30, 30, TimeUnit.SECONDS);
    }

    /**
     * 注册会话
     */
    public void registerSession(String sessionId, WebSocketSession session) {
        sessions.put(sessionId, session);
        log.info("WebSocket 会话注册成功: {}, 当前会话数: {}", sessionId, sessions.size());
    }

    /**
     * 绑定设备与会话
     */
    public synchronized boolean bindPhone(String sessionId,String account,String device,String install,String name) {
        String slot=account+":"+(install==null?"legacy":install);
        Phone prior=phones.get(sessionId);
        if(prior!=null)return prior.slot.equals(slot) && java.util.Objects.equals(prior.device,device);
        if(!sessions.containsKey(sessionId)||slots.putIfAbsent(slot,sessionId)!=null)return false;
        phones.put(sessionId,new Phone(account,device,name,slot));return true;
    }
    public String getDeviceId(String sessionId){Phone p=phones.get(sessionId);return p==null?null:p.account;}
    public boolean joinedDemo(String sessionId,String device){Phone p=phones.get(sessionId);
        return p!=null && device!=null && device.equals(openDemoDevice) && device.equals(p.device);}
    public String displayName(String sessionId){Phone p=phones.get(sessionId);return p==null?"值班手机":p.name;}
    public java.util.List<String> recipients(String account,String device){
        java.util.List<String> found=new java.util.ArrayList<>();
        phones.forEach((sid,p)->{if((p.account.equals(account) || joinedDemo(sid,device)) && (device==null || p.device==null || device.equals(p.device)) && hasSession(sid))found.add(sid);});
        return found;
    }
    public synchronized String removeSession(String sessionId){
        sessions.remove(sessionId);Phone p=phones.remove(sessionId);
        if(p!=null)slots.remove(p.slot,sessionId);
        return p==null?null:sessionId;
    }
    /**
     * 发送消息到指定会话
     */
    public boolean sendMessageToSession(String sessionId, String message) {
        WebSocketSession session = sessions.get(sessionId);
        if (session != null && session.isOpen()) {
            try {
                synchronized(session){session.sendMessage(new TextMessage(message));}
                log.debug("发送消息到会话 {}: {}", sessionId, message);
                return true;
            } catch (IOException | IllegalStateException e) {
                log.error("发送消息到会话 {} 失败", sessionId, e);
            }
        } else {
            log.warn("会话 {} 不存在或已关闭", sessionId);
        }
        return false;
    }

    /**
     * 发送消息到指定设备
     */
    public boolean sendMessageToDevice(String deviceId, String message) {
        boolean sent=false;
        for(String sid:recipients(deviceId,null))sent |= sendMessageToSession(sid,message);
        return sent;
    }

    /**
     * 广播消息到所有会话
     */
    public void broadcastMessage(String message) {
        sessions.forEach((sessionId, session) -> {
            if (session.isOpen()) {
                try {
                    session.sendMessage(new TextMessage(message));
                } catch (IOException e) {
                    log.error("广播消息到会话 {} 失败", sessionId, e);
                }
            }
        });
    }

    /**
     * 获取当前会话数
     */
    public int getSessionCount() {
        return sessions.size();
    }

    /**
     * 清理不活跃的会话
     */
    private void cleanupInactiveSessions() {
        sessions.entrySet().removeIf(entry -> {
            WebSocketSession session = entry.getValue();
            if (!session.isOpen()) {
                String sessionId = entry.getKey();
                log.info("清理不活跃会话: {}", sessionId);
                return true;
            }
            return false;
        });
    }

    /**
     * 检查会话是否存在
     */
    public boolean hasSession(String sessionId) {
        WebSocketSession session = sessions.get(sessionId);
        return session != null && session.isOpen();
    }
}
