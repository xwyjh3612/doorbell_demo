package com.youkong.audio_server.service;
import java.util.concurrent.ConcurrentHashMap;

/** Route legacy ESP32 replies without target to the client that sent the offer. */
final class CallReplyRoutes {
    private static final class Route {
        final String client; final long at;
        Route(String client) { this.client=client; at=System.currentTimeMillis(); }
    }
    private final ConcurrentHashMap<String,Route> routes=new ConcurrentHashMap<>();
    void begin(String device,String client){
        if(device==null||client==null)return;
        if(routes.containsKey(device)||routes.size()<256)routes.put(device,new Route(client));
    }
    String reply(String device,String fallback){
        Route route=device==null?null:routes.get(device);
        if(route==null)return fallback;
        // Keep reply routing through normal long calls; only discard abandoned
        // routes after two hours. Explicit hangup/reject clears immediately.
        if(System.currentTimeMillis()-route.at>2*60*60*1000L){routes.remove(device,route);return fallback;}
        return route.client;
    }
    void end(String device){if(device!=null)routes.remove(device);}
}
