package com.youkong.voiceintercom;

import android.animation.ValueAnimator;
import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.drawable.Drawable;
import android.os.Build;
import android.view.View;
import android.view.animation.LinearInterpolator;

/** A short handset trill, then a quiet interval as the two rings travel out. */
final class IncomingPulseView extends View {
    private final Paint pen=new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Drawable handset;
    private final ValueAnimator loop=ValueAnimator.ofFloat(0f,1f);
    private boolean ringing,visible;
    private float phase;
    IncomingPulseView(Context context){
        super(context);handset=context.getDrawable(R.drawable.ic_ringing_handset);setContentDescription("来电听筒");
        loop.setDuration(1800);loop.setRepeatCount(ValueAnimator.INFINITE);loop.setInterpolator(new LinearInterpolator());
        loop.addUpdateListener(a->{phase=(float)a.getAnimatedValue();invalidate();});
    }
    void setRinging(boolean enabled){ringing=enabled;refresh();}
    @Override public void onVisibilityAggregated(boolean shown){super.onVisibilityAggregated(shown);visible=shown;refresh();}
    @Override protected void onDetachedFromWindow(){visible=false;refresh();super.onDetachedFromWindow();}
    private void refresh(){
        boolean motion=Build.VERSION.SDK_INT>=26?ValueAnimator.areAnimatorsEnabled():android.provider.Settings.Global.getFloat(getContext().getContentResolver(),android.provider.Settings.Global.ANIMATOR_DURATION_SCALE,1f)>0;
        if(ringing && visible && isAttachedToWindow() && motion){if(!loop.isStarted())loop.start();}
        else if(loop.isStarted()){loop.cancel();phase=0;invalidate();}
    }
    @Override protected void onDraw(Canvas c){
        super.onDraw(c);float r=Math.min(getWidth(),getHeight())*.235f;if(r<=0)return;
        float x=getWidth()*.5f,y=getHeight()*.5f;c.save();c.translate(x,y);
        for(int i=0;i<2;i++){float f=(phase+i*.5f)%1f;pen.setStyle(Paint.Style.STROKE);pen.setStrokeWidth(r*.025f);pen.setColor(0xff69efd2);pen.setAlpha((int)(90*(1-f)));c.drawCircle(0,0,r*(1.08f+.88f*f),pen);}
        pen.setStyle(Paint.Style.FILL);pen.setColor(0xff19504f);c.drawCircle(0,0,r,pen);pen.setStyle(Paint.Style.STROKE);pen.setColor(0xff52cbaf);pen.setStrokeWidth(r*.032f);c.drawCircle(0,0,r,pen);
        float trill=phase<.44f?(float)(Math.sin(phase/.44f*Math.PI)*Math.sin(phase/.44f*6*Math.PI)):0;
        c.rotate(11*trill);int size=Math.round(r*.54f);handset.setBounds(-size,-size,size,size);handset.draw(c);c.restore();
    }
}
