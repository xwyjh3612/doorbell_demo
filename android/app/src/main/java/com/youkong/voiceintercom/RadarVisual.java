package com.youkong.voiceintercom;
import android.content.Context;
import android.graphics.*;
import android.view.View;

/** Decorative radar rings around the actual reported target state. */
final class RadarVisual extends View {
    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private String label = "等待感知数据";
    private boolean live;
    RadarVisual(Context context) { super(context); setContentDescription(label); }
    void state(String label, boolean live) {
        if(this.label.equals(label)&&this.live==live)return;
        this.label = label; this.live = live; setContentDescription("雷达：" + label); invalidate();
    }
    @Override protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);
        float d = getResources().getDisplayMetrics().density, cx = getWidth()/2f, cy = getHeight()/2f - 10*d;
        float radius = Math.min(getWidth()/2.6f, getHeight()/2.15f);
        int cyan = live ? Color.rgb(70,225,207) : Color.rgb(93,124,149);
        paint.setStyle(Paint.Style.FILL);
        paint.setShader(new RadialGradient(cx,cy,radius,new int[]{0x203bddc3,0x003bddc3},null,Shader.TileMode.CLAMP));
        canvas.drawCircle(cx,cy,radius,paint); paint.setShader(null);
        paint.setStyle(Paint.Style.STROKE); paint.setStrokeWidth(d);
        for(int i=1;i<=3;i++){paint.setColor(Color.argb(35+i*8,75,174,195));canvas.drawCircle(cx,cy,radius*i/3,paint);}
        if(live){
            paint.setColor(cyan);paint.setStrokeWidth(2*d);
            canvas.drawArc(cx-radius,cy-radius,cx+radius,cy+radius,305,48,false,paint);
        }
        paint.setColor(cyan);paint.setStrokeWidth(2.5f*d);
        canvas.drawRoundRect(cx-6*d,cy-25*d,cx+6*d,cy-4*d,6*d,6*d,paint);
        canvas.drawArc(cx-12*d,cy-21*d,cx+12*d,cy+2*d,0,180,false,paint);
        canvas.drawLine(cx,cy+2*d,cx,cy+9*d,paint);canvas.drawLine(cx-7*d,cy+9*d,cx+7*d,cy+9*d,paint);
        paint.setStyle(Paint.Style.FILL);paint.setColor(Color.rgb(220,235,243));paint.setTextSize(16*d);paint.setTextAlign(Paint.Align.CENTER);
        canvas.drawText(label,cx,cy+39*d,paint);
    }
}
