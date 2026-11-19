package com.youkong.voiceintercom;
import android.content.Context;
import android.graphics.*;
import android.view.View;
import java.util.ArrayDeque;

/** Only plots received numerical measurements, never synthesized waveforms. */
final class TrendView extends View {
    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final ArrayDeque<Sample> samples = new ArrayDeque<>();
    private final int color, maximum;
    private static final class Sample {
        final long at; final int value;
        Sample(long at,int value){this.at=at;this.value=value;}
    }
    TrendView(Context context,int color,int maximum){super(context);this.color=color;this.maximum=maximum;setContentDescription("最近两分钟实际上报数值趋势");}
    void add(long at,int value){samples.addLast(new Sample(at,value));while(samples.size()>60)samples.removeFirst();invalidate();}
    void clear(){samples.clear();invalidate();}
    @Override protected void onDraw(Canvas c){
        long now=android.os.SystemClock.elapsedRealtime(), start=now-120000;
        float d=getResources().getDisplayMetrics().density,w=getWidth(),h=getHeight();
        paint.setStrokeWidth(d);paint.setColor(0x202f7f9f);
        for(int i=1;i<=3;i++)c.drawLine(0,h*i/4,w,h*i/4,paint);
        Sample previous=null;paint.setStrokeWidth(2*d);
        for(Sample s:samples){
            if(s.at<start)continue;
            if(s.value<=0){previous=null;continue;}
            float x=w*(s.at-start)/120000f,y=h-6*d-(h-12*d)*s.value/maximum;
            paint.setColor(color);
            if(previous!=null&&s.at-previous.at<15000)c.drawLine(w*(previous.at-start)/120000f,h-6*d-(h-12*d)*previous.value/maximum,x,y,paint);
            c.drawCircle(x,y,2*d,paint);previous=s;
        }
    }
}
