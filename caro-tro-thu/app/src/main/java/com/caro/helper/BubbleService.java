package com.caro.helper;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.PixelFormat;
import android.graphics.drawable.GradientDrawable;
import android.os.Build;
import android.os.IBinder;
import android.os.VibrationEffect;
import android.os.Vibrator;
import android.util.DisplayMetrics;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.WindowManager;
import android.widget.LinearLayout;
import android.widget.TextView;

/**
 * BONG BÓNG NỔI kiểu tin nhắn (như chat head của Messenger): một nút tròn nhỏ luôn nổi trên các app khác,
 * tới lượt bạn thì bật ra một "tin nhắn" hiện toạ độ nước đi, ví dụ  "👉 Bạn đánh ô  G9".
 * Chỉ hiện khi app đang ở nền (đang xem TikTok...). Kéo để di chuyển, chạm để mở lại app.
 * Chỉ lo phần hiển thị; nội dung do trang web trong app gửi sang qua MainActivity (cầu nối JavaScript).
 */
public class BubbleService extends Service {
    static final String ACTION_SHOW = "com.caro.helper.SHOW";
    static final String ACTION_IDLE = "com.caro.helper.IDLE";
    static final String ACTION_VISIBLE = "com.caro.helper.VISIBLE";
    static final String ACTION_STOP = "com.caro.helper.STOP";
    private static final String CHANNEL = "caro_bubble";

    private WindowManager wm;
    private LinearLayout root;
    private TextView head;
    private LinearLayout msg;
    private TextView msgSmall;
    private TextView msgBig;
    private WindowManager.LayoutParams lp;
    private boolean appVisible = true;
    private boolean msgOnRight = true;
    private boolean hasMsg = false;
    private boolean added = false;
    private String lastKey = "";
    static volatile boolean running = false;

    // ---- gọi từ MainActivity ----
    static void send(Context c, String action, String small, String big, String kind) {
        Intent i = new Intent(c, BubbleService.class).setAction(action);
        if (small != null) i.putExtra("small", small);
        if (big != null) i.putExtra("big", big);
        if (kind != null) i.putExtra("kind", kind);
        if (Build.VERSION.SDK_INT >= 26 && !ACTION_STOP.equals(action)) c.startForegroundService(i);
        else c.startService(i);
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    private int dp(float v) {
        return (int) TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v, getResources().getDisplayMetrics());
    }

    @Override
    public void onCreate() {
        super.onCreate();
        wm = (WindowManager) getSystemService(WINDOW_SERVICE);
        startForeground(7, buildNotification());
        buildViews();
        running = true;
    }

    private Notification buildNotification() {
        NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        if (Build.VERSION.SDK_INT >= 26 && nm != null) {
            nm.createNotificationChannel(new NotificationChannel(CHANNEL, "Bong bóng gợi ý", NotificationManager.IMPORTANCE_MIN));
        }
        Intent open = new Intent(this, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_REORDER_TO_FRONT);
        int fl = Build.VERSION.SDK_INT >= 23 ? PendingIntent.FLAG_IMMUTABLE : 0;
        PendingIntent pi = PendingIntent.getActivity(this, 0, open, fl);
        Notification.Builder b = Build.VERSION.SDK_INT >= 26 ? new Notification.Builder(this, CHANNEL) : new Notification.Builder(this);
        b.setContentTitle("Caro Trợ Thủ đang gợi ý nước đi").setContentText("Bong bóng nổi đang bật. Chạm để mở app.").setSmallIcon(R.drawable.ic_launcher).setContentIntent(pi).setOngoing(true);
        return b.build();
    }

    private GradientDrawable shape(int color, float radiusDp, boolean oval) {
        GradientDrawable g = new GradientDrawable();
        g.setColor(color);
        if (oval) g.setShape(GradientDrawable.OVAL);
        else g.setCornerRadius(dp(radiusDp));
        return g;
    }

    private void buildViews() {
        root = new LinearLayout(this);
        root.setOrientation(LinearLayout.HORIZONTAL);
        root.setGravity(Gravity.CENTER_VERTICAL);

        head = new TextView(this);
        head.setText("♟");
        head.setTextColor(Color.WHITE);
        head.setTextSize(TypedValue.COMPLEX_UNIT_SP, 26);
        head.setGravity(Gravity.CENTER);
        head.setBackground(shape(Color.parseColor("#2F6FE0"), 0, true));
        head.setElevation(dp(6));

        msg = new LinearLayout(this);
        msg.setOrientation(LinearLayout.VERTICAL);
        msg.setPadding(dp(16), dp(8), dp(16), dp(8));
        msg.setElevation(dp(6));
        msgSmall = new TextView(this);
        msgSmall.setTextColor(Color.WHITE);
        msgSmall.setTextSize(TypedValue.COMPLEX_UNIT_SP, 13);
        msgBig = new TextView(this);
        msgBig.setTextColor(Color.WHITE);
        msgBig.setTextSize(TypedValue.COMPLEX_UNIT_SP, 34);
        msgBig.setTypeface(msgBig.getTypeface(), android.graphics.Typeface.BOLD);
        msg.addView(msgSmall);
        msg.addView(msgBig);
        msg.setVisibility(View.GONE);

        arrange();

        lp = new WindowManager.LayoutParams(
                WindowManager.LayoutParams.WRAP_CONTENT,
                WindowManager.LayoutParams.WRAP_CONTENT,
                Build.VERSION.SDK_INT >= 26 ? WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY : WindowManager.LayoutParams.TYPE_PHONE,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE | WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
                PixelFormat.TRANSLUCENT);
        lp.gravity = Gravity.TOP | Gravity.START;
        lp.x = dp(8);
        lp.y = dp(220);

        root.setOnTouchListener(new View.OnTouchListener() {
            private int sx, sy;
            private float tx, ty;
            private boolean moved;

            @Override
            public boolean onTouch(View v, MotionEvent e) {
                switch (e.getAction()) {
                    case MotionEvent.ACTION_DOWN:
                        sx = lp.x; sy = lp.y; tx = e.getRawX(); ty = e.getRawY(); moved = false;
                        return true;
                    case MotionEvent.ACTION_MOVE:
                        float dx = e.getRawX() - tx;
                        float dy = e.getRawY() - ty;
                        if (Math.abs(dx) > dp(6) || Math.abs(dy) > dp(6)) moved = true;
                        if (moved) {
                            lp.x = Math.max(0, sx + (int) dx);
                            lp.y = Math.max(0, sy + (int) dy);
                            try { wm.updateViewLayout(root, lp); } catch (Exception ex) { /* bỏ qua */ }
                        }
                        return true;
                    case MotionEvent.ACTION_UP:
                        if (!moved) {
                            Intent open = new Intent(BubbleService.this, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_REORDER_TO_FRONT);
                            startActivity(open);
                        } else {
                            arrange(); // kéo xong thì xếp lại: tin nhắn nằm về phía còn chỗ trống
                        }
                        return true;
                    default:
                        return false;
                }
            }
        });
    }

    /** Xếp lại: nút tròn + tin nhắn. Nếu bong bóng nằm nửa phải màn hình thì tin nhắn hiện bên trái nút tròn. */
    private void arrange() {
        DisplayMetrics dm = getResources().getDisplayMetrics();
        boolean right = lp == null || lp.x < dm.widthPixels / 2;
        if (root.getChildCount() == 2 && right == msgOnRight) return;
        msgOnRight = right;
        root.removeAllViews();
        LinearLayout.LayoutParams hp = new LinearLayout.LayoutParams(dp(54), dp(54));
        LinearLayout.LayoutParams mp = new LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        if (right) {
            mp.leftMargin = dp(8);
            root.addView(head, hp);
            root.addView(msg, mp);
        } else {
            mp.rightMargin = dp(8);
            root.addView(msg, mp);
            root.addView(head, hp);
        }
    }

    private void attach() {
        if (added) return;
        try {
            wm.addView(root, lp);
            added = true;
        } catch (Exception e) {
            // chưa được cấp quyền "hiển thị trên các ứng dụng khác"
            stopSelf();
        }
    }

    private void applyVisibility() {
        if (!added) return;
        root.setVisibility(appVisible ? View.GONE : View.VISIBLE);
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent == null || intent.getAction() == null) return START_STICKY;
        String a = intent.getAction();
        if (ACTION_STOP.equals(a)) {
            stopForeground(true);
            stopSelf();
            return START_NOT_STICKY;
        }
        attach();
        if (ACTION_VISIBLE.equals(a)) {
            appVisible = "1".equals(intent.getStringExtra("small"));
        } else if (ACTION_IDLE.equals(a)) {
            hasMsg = false;
            msg.setVisibility(View.GONE);
            lastKey = "";
        } else if (ACTION_SHOW.equals(a)) {
            String small = intent.getStringExtra("small");
            String big = intent.getStringExtra("big");
            String kind = intent.getStringExtra("kind");
            int color = Color.parseColor("nhay".equals(kind) ? "#7B3FC4" : "me".equals(kind) ? "#1F8F4E" : "#33415F");
            msg.setBackground(shape(color, 22, false));
            msgSmall.setText(small == null ? "" : small);
            msgBig.setText(big == null ? "" : big);
            arrange();
            msg.setVisibility(View.VISIBLE);
            String key = kind + "|" + small + "|" + big;
            if (!key.equals(lastKey)) {
                lastKey = key;
                popIn();
                if ("me".equals(kind) || "nhay".equals(kind)) buzz();
            }
            hasMsg = true;
        }
        applyVisibility();
        return START_STICKY;
    }

    private void popIn() {
        msg.setScaleX(0.6f);
        msg.setScaleY(0.6f);
        msg.setAlpha(0f);
        msg.animate().scaleX(1f).scaleY(1f).alpha(1f).setDuration(220).start();
        head.animate().scaleX(1.18f).scaleY(1.18f).setDuration(120).withEndAction(new Runnable() {
            @Override
            public void run() {
                head.animate().scaleX(1f).scaleY(1f).setDuration(160).start();
            }
        }).start();
    }

    private void buzz() {
        try {
            Vibrator v = (Vibrator) getSystemService(VIBRATOR_SERVICE);
            if (v == null || !v.hasVibrator()) return;
            if (Build.VERSION.SDK_INT >= 26) v.vibrate(VibrationEffect.createOneShot(80, VibrationEffect.DEFAULT_AMPLITUDE));
            else v.vibrate(80);
        } catch (Exception e) {
            /* bỏ qua */
        }
    }

    @Override
    public void onDestroy() {
        running = false;
        if (added) {
            try { wm.removeView(root); } catch (Exception e) { /* bỏ qua */ }
            added = false;
        }
        super.onDestroy();
    }
}
