package com.youkong.voiceintercom;

import android.content.Context;
import android.graphics.*;
import android.view.MotionEvent;
import android.view.View;
import org.json.JSONArray;
import org.json.JSONObject;
import java.text.SimpleDateFormat;
import java.util.*;

/** Time-proportional segments, including explicit unknown gaps; tap to inspect. */
final class PresenceTimeline extends View {
    static final class Segment {
        final long from, to; final String state;
        Segment(long from,long to,String state){this.from=from;this.to=to;this.state=state;}
    }
    static final class History {
        long from,to;
        boolean healthy;
        final List<Segment> segments=new ArrayList<>();
        static History parse(JSONObject data) throws Exception {
            History result=new History();result.from=data.getLong("from_ms");result.to=data.getLong("to_ms");result.healthy=data.optBoolean("storage_ok",false);
            JSONArray items=data.getJSONArray("segments");
            for(int i=0;i<items.length();i++){JSONObject item=items.getJSONObject(i);long start=item.getLong("from_ms"),end=item.getLong("to_ms");
                if(start>=result.from && end<=result.to && end>start)result.segments.add(new Segment(start,end,item.getString("state")));}
            return result;
        }
    }
    private final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);
    private History history=new History();
    private Segment selected;
    private java.util.function.Consumer<Segment> listener;
    PresenceTimeline(Context context){super(context);setContentDescription("感知时间线，等待历史记录");}
    static int color(String state){switch(state){case "moving":return 0xff75bcff;case "still":return 0xff43e2c7;case "absent":return 0xff8aa7bf;case "present":return 0xffffce7b;default:return 0xff2a3b50;}}
    static String label(String state){return state.equals("unknown")?"无数据":RadarVisual.label(state);}
    static String time(long at){return new SimpleDateFormat("HH:mm:ss",Locale.CHINA).format(new Date(at));}
    static String duration(long ms){long sec=Math.max(0,ms/1000);return sec>=3600?String.format(Locale.CHINA,"%d 小时 %d 分",sec/3600,sec%3600/60):sec>=60?String.format(Locale.CHINA,"%d 分 %d 秒",sec/60,sec%60):sec+" 秒";}
    void data(History history,java.util.function.Consumer<Segment> listener){this.history=history;this.listener=listener;selected=null;setContentDescription("感知时间线，共 "+history.segments.size()+" 个状态时段，点击查看时间与状态");invalidate();}
    @Override protected void onDraw(Canvas canvas){
        float d=getResources().getDisplayMetrics().density,width=getWidth(),start=2*d,end=width-2*d;
        paint.setStyle(Paint.Style.FILL);paint.setColor(0xff2a3b50);canvas.drawRoundRect(start,14*d,end,42*d,7*d,7*d,paint);
        if(history.to>history.from){
            canvas.save();Path clip=new Path();clip.addRoundRect(new RectF(start,14*d,end,42*d),7*d,7*d,Path.Direction.CW);canvas.clipPath(clip);
            for(Segment s:history.segments){float x=start+(end-start)*(s.from-history.from)/(float)(history.to-history.from),right=start+(end-start)*(s.to-history.from)/(float)(history.to-history.from);
                paint.setColor(color(s.state));canvas.drawRect(x,14*d,right,42*d,paint);}
            canvas.restore();
            paint.setTextSize(10*d);paint.setColor(0xff859cb5);
            SimpleDateFormat format=new SimpleDateFormat("HH:mm",Locale.CHINA);
            for(int i=0;i<=2;i++){paint.setTextAlign(i==0?Paint.Align.LEFT:i==2?Paint.Align.RIGHT:Paint.Align.CENTER);canvas.drawText(format.format(new Date(history.from+(history.to-history.from)*i/2)),start+(end-start)*i/2,62*d,paint);}
            if(selected!=null){float x=start+(end-start)*((selected.from+selected.to)/2-history.from)/(float)(history.to-history.from);paint.setColor(0xffe2edf9);paint.setStrokeWidth(2*d);canvas.drawLine(x,8*d,x,46*d,paint);}
        }
    }
    @Override public boolean onTouchEvent(MotionEvent event){
        if(event.getAction()==MotionEvent.ACTION_DOWN)return true;
        if(event.getAction()==MotionEvent.ACTION_UP && history.to>history.from){performClick();long at=history.from+(long)(Math.max(0,Math.min(1,event.getX()/getWidth()))*(history.to-history.from));
            for(Segment segment:history.segments){if(at>=segment.from && at<=segment.to){selected=segment;invalidate();if(listener!=null)listener.accept(segment);break;}}return true;}
        return super.onTouchEvent(event);
    }
    @Override public boolean performClick(){super.performClick();return true;}
}
