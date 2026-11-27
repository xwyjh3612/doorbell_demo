package com.youkong.audio_server.service;

import com.youkong.audio_server.dto.SignalingMessage;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.function.LongSupplier;
import java.util.function.Consumer;

final class CallReplyRoutes {
    interface Delivery {
        default List<String> recipients(String group,String device){return Collections.singletonList(group);}
        default String account(String endpoint){return endpoint;}
        default String name(String endpoint){return endpoint;}
        boolean phone(String client, SignalingMessage message);
        boolean device(String device, SignalingMessage message);
        void alert(String device, String client, String key, long at);
    }
    private static final class Line {
        String device, group, owner, id;
        final Set<String> members=new LinkedHashSet<>(); // ringing phones, or the single owner
        boolean groupInvite, acceptSent;
        boolean fromDevice, offered, answered;
        long created, deviceTimestamp=Long.MIN_VALUE;
    }
    private final Map<String,Line> devices=new HashMap<>(), clients=new HashMap<>();
    private final Map<String,Long> recent=new LinkedHashMap<>(), drain=new HashMap<>();
    private final LongSupplier clock;
    private final Object[] lanes=new Object[128];
    CallReplyRoutes(LongSupplier clock){this.clock=clock;Arrays.setAll(lanes,index->new Object());}
    private Object lane(String device){return lanes[Math.floorMod(device.hashCode(),lanes.length)];}
    static boolean start(SignalingMessage m){return "offer".equals(m.getType()) || "ring".equals(m.getType()) || command(m,"RING");}
    static boolean command(SignalingMessage m,String cmd){return "customized".equals(m.getType()) && cmd.equals(m.getData());}
    static boolean terminal(SignalingMessage m){return Arrays.asList("bye","reject","timeout").contains(m.getType()) || command(m,"REJECT_CALL") || command(m,"CLOSE");}
    static boolean control(SignalingMessage m){return "claim".equals(m.getType())||start(m)||terminal(m)||command(m,"ACCEPT_CALL")||"answer".equals(m.getType())||"candidate".equals(m.getType());}
    private static String fingerprint(String... fields){return UUID.nameUUIDFromBytes(String.join("\u0000",fields).getBytes(StandardCharsets.UTF_8)).toString();}
    private boolean seen(String key,long now){
        recent.entrySet().removeIf(entry->entry.getValue()<now);
        if(recent.containsKey(key))return true;
        if(recent.size()>=8192)recent.remove(recent.keySet().iterator().next());
        recent.put(key,now+120000);return false;
    }
    private void release(Line line,long now){devices.remove(line.device,line);for(String p:line.members)clients.remove(p,line);drain.put(line.device,now+2000);}
    static SignalingMessage notice(String type,String from,String to,String id,String reason,long at){
        SignalingMessage value=new SignalingMessage();value.setType(type);value.setFrom(from);value.setTarget(to);
        value.setCallId(id);value.setData(reason);value.setTimestamp(at/1000);return value;
    }
    private void tell(Line line,String endpoint,SignalingMessage msg,Delivery out){
        out.phone(endpoint,msg.routed(line.device,line.group,line.id));
    }
    private void sendDevice(Line line,SignalingMessage msg,Delivery out){
        out.device(line.device,msg.routed(line.group,line.device,null));
    }
    void expire(Delivery out){
        long now=clock.getAsLong();List<Line> expired=new ArrayList<>();
        synchronized(this){drain.entrySet().removeIf(entry->entry.getValue()<=now);for(Line l:devices.values())if(!l.answered && now-l.created>=75000)expired.add(l);}
        for(Line l:expired)synchronized(lane(l.device)){
            synchronized(this){if(devices.get(l.device)!=l || l.answered)continue;release(l,now);}
            for(String p:l.members)tell(l,p,notice("timeout",null,null,null,"timeout",now),out);
            sendDevice(l,notice("bye",null,null,null,"timeout",now),out);
        }
    }
    void disconnected(String endpoint,Delivery out){
        Line l;synchronized(this){l=clients.get(endpoint);}if(l==null)return;
        synchronized(lane(l.device)){
            synchronized(this){if(clients.get(endpoint)!=l)return;clients.remove(endpoint,l);l.members.remove(endpoint);
                if(!l.members.isEmpty())return;release(l,clock.getAsLong());}
            sendDevice(l,notice("bye",null,null,null,"offline",clock.getAsLong()),out);
        }
    }
    void route(boolean up,String device,String client,SignalingMessage msg,Delivery out){
        synchronized(lane(device)){
            List<Consumer<Delivery>> pending=new ArrayList<>();
            synchronized(this){transition(up,device,client,msg,out,pending);}
            for(Consumer<Delivery> action:pending)action.accept(out);
        }
    }
    // Device lane is held while delivering. Other devices can ring independently.
    private void transition(boolean up,String device,String client,SignalingMessage msg,Delivery out,List<Consumer<Delivery>> pending){
        long now=clock.getAsLong();String type=msg.getType(),tag=msg.getCallId();Line l=devices.get(device);
        if(start(msg)){
            String key=fingerprint(up?"up":"down",device,client,type,tag==null?String.valueOf(msg.getTimestamp()):tag,String.valueOf(msg.getData()));
            if(seen(key,now))return;
            if(l!=null && l.fromDevice==up && (up || (l.members.contains(client) && Objects.equals(l.id,tag)))){
                if(!l.offered && "offer".equals(type)){l.offered=true;forward(up,l,msg,pending);}return;
            }
            if(up)pending.add(d->d.alert(device,client,key,now));
            boolean crossed=l!=null && l.fromDevice!=up && !l.answered && (up ? l.group.equals(client)
                    : l.owner==null && !l.groupInvite && l.members.contains(client));
            if(crossed){
                release(l,now);pending.add(d->{for(String p:l.members)d.phone(p,notice("reject",device,l.group,l.fromDevice?tag:l.id,"busy",now));
                    sendDevice(l,notice("reject",null,null,null,"busy",now),d);});return;
            }
            if(l!=null || now<drain.getOrDefault(device,0L) || !up && clients.containsKey(client)){
                if(!up)pending.add(d->d.phone(client,notice("reject",device,out.account(client),tag,"busy",now)));
                else if(l==null)pending.add(d->d.device(device,notice("reject",client,device,null,"busy",now)));
                return;
            }
            Line n=new Line();n.device=device;n.group=up?client:out.account(client);if(n.group==null)return;
            n.fromDevice=up;n.created=now;n.id=up || tag==null?UUID.randomUUID().toString():tag;n.offered="offer".equals(type);
            if(up){
                if(msg.getTimestamp()!=null)n.deviceTimestamp=msg.getTimestamp();
                List<String> endpoints=out.recipients(client,device);n.groupInvite=endpoints.size()>1;
                for(String p:endpoints)if(!clients.containsKey(p))n.members.add(p);
                if(n.members.isEmpty()){String why=endpoints.isEmpty()?"offline":"busy";
                    pending.add(d->sendDevice(n,notice("reject",null,null,null,why,now),d));return;}
            }else{n.owner=client;n.members.add(client);}
            devices.put(device,n);for(String p:n.members)clients.put(p,n);
            pending.add(d->{if(up){
                for(String p:new ArrayList<>(n.members))if(!d.phone(p,msg.routed(device,n.group,n.id))){
                    synchronized(this){clients.remove(p,n);n.members.remove(p);}}
                if(!n.members.isEmpty())return;
            }else if(d.device(device,msg.routed(n.group,device,null)))return;
                synchronized(this){release(n,clock.getAsLong());}
                SignalingMessage offline=notice("reject",null,null,null,"offline",now);
                if(up)sendDevice(n,offline,d);else tell(n,client,offline,d);
            });return;
        }
        if(l==null || (!up && (!l.members.contains(client) || tag!=null && !tag.equals(l.id) || l.groupInvite && tag==null)))return;
        if(up && msg.getTimestamp()!=null && msg.getTimestamp()<l.deviceTimestamp)return;
        if(up && terminal(msg) && seen(fingerprint("end",device,type,String.valueOf(msg.getTimestamp())),now))return;
        boolean claim="claim".equals(type),answer="answer".equals(type),accept=command(msg,"ACCEPT_CALL");
        if(claim && (up || !l.fromDevice || !l.id.equals(tag)))return;
        if(answer && (up==l.fromDevice || !l.offered || l.answered))return;
        if(accept && (up==l.fromDevice || l.acceptSent))return;
        if(!up && l.fromDevice && l.owner==null){
            if(claim || answer || accept){
                l.owner=client;
                final String name=out.name(client);
                for(String p:new ArrayList<>(l.members))if(!p.equals(client)){
                    l.members.remove(p);clients.remove(p,l);
                    pending.add(d->{SignalingMessage lost=notice("reject",device,l.group,l.id,"answered_elsewhere",now);
                        lost.setAnsweredBy(name);d.phone(p,lost);});
                }
            }else if(terminal(msg)){
                if(l.members.size()>1){l.members.remove(client);clients.remove(client,l);return;}
            }else return; // No telephone may send ICE to the device before it owns this call.
        }
        if(claim){pending.add(d->tell(l,client,notice("claim_granted",null,null,null,null,now),d));return;}
        if(answer){l.answered=true;if(up && msg.getTimestamp()!=null)l.deviceTimestamp=msg.getTimestamp();}
        if(accept)l.acceptSent=true;
        if(terminal(msg))release(l,now);
        forward(up,l,msg,pending);
    }
    private void forward(boolean up,Line l,SignalingMessage msg,List<Consumer<Delivery>> pending){
        if(up){for(String p:l.members)pending.add(d->tell(l,p,msg,d));}
        else pending.add(d->sendDevice(l,msg,d));
    }
}
