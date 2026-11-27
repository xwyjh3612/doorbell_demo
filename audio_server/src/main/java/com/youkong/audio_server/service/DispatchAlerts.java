package com.youkong.audio_server.service;

import com.alibaba.fastjson.JSON;
import com.alibaba.fastjson.JSONArray;
import com.alibaba.fastjson.JSONObject;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class DispatchAlerts {
    private final Path directory;
    private final Map<String,String> recipients=new HashMap<>();
    public DispatchAlerts(@Value("${signaling.alert-directory:./data/call-alerts}") String directory,
                          @Value("${signaling.dispatch:189833342344184=web_client_001}") String bindings){
        this.directory=Paths.get(directory);
        for(String item:bindings.split(",")){
            String[] pair=item.trim().split("=",-1);
            if(pair.length!=2 || !valid(pair[0]) || !valid(pair[1]) || recipients.put(pair[0],pair[1])!=null)
                throw new IllegalArgumentException("Invalid or duplicate signaling.dispatch device");
        }
    }
    public static boolean valid(String id){return id!=null && id.matches("[A-Za-z0-9_-]{1,64}");}
    public String recipient(String device){return recipients.get(device);}
    private Path file(String client,String device){
        if(!valid(client)||!valid(device))throw new IllegalArgumentException("Invalid endpoint");
        return directory.resolve(client).resolve(device+".json");
    }
    public synchronized JSONArray history(String client,String device) throws IOException{
        if(!client.equals(recipient(device)))return new JSONArray();
        Path target=file(client,device);return Files.exists(target)?JSON.parseArray(new String(Files.readAllBytes(target),StandardCharsets.UTF_8)):new JSONArray();
    }
    synchronized JSONObject record(String device,String client,String id,long at) throws IOException{
        if(!client.equals(recipient(device)))return null;
        JSONArray events=history(client,device);
        for(int i=0;i<events.size();i++)if(id.equals(events.getJSONObject(i).getString("id")))return null;
        JSONObject event=new JSONObject();event.put("id",id);event.put("device",device);event.put("at_ms",at);
        events.add(0,event);if(events.size()>100)events.remove(events.size()-1);
        Path target=file(client,device);Files.createDirectories(target.getParent());Path stage=target.resolveSibling(target.getFileName()+".tmp");
        Files.write(stage,events.toJSONString().getBytes(StandardCharsets.UTF_8));
        Files.move(stage,target,StandardCopyOption.ATOMIC_MOVE,StandardCopyOption.REPLACE_EXISTING);return event;
    }
}
