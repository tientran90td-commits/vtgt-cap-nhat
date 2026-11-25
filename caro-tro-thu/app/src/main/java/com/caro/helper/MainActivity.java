package com.caro.helper;

import android.app.Activity;
import android.content.Intent;
import android.os.Build;
import android.provider.Settings;
import android.webkit.JavascriptInterface;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.widget.FrameLayout;
import android.graphics.PixelFormat;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import java.io.InputStream;
import java.util.HashMap;
import java.util.Map;

/**
 * Vỏ app: mở trang assets/index.html qua địa chỉ ảo https://appassets.androidplatform.net/ (không cần mạng).
 * Dùng địa chỉ https (thay vì file://) để chạy được engine Rapfi (WebAssembly) nằm trong assets/rapfi/.
 * Từ v2: app nối vào game Caro LIVE (http://địa-chỉ:3000) nên cần quyền INTERNET + cho phép http/ws.
 */
public class MainActivity extends Activity {
    private static final String HOST = "appassets.androidplatform.net";
    private WebView web;

    /** Cầu nối cho trang web trong app điều khiển BONG BÓNG NỔI (xem BubbleService.java). Trang gọi: AndroidBubble.xxx() */
    public class BubbleBridge {
        /** "ok" = bật được; "need_overlay" = chưa cấp quyền hiển thị trên các ứng dụng khác (đã mở màn hình cấp quyền). */
        @JavascriptInterface
        public String enable() {
            if (Build.VERSION.SDK_INT >= 23 && !Settings.canDrawOverlays(MainActivity.this)) {
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        try {
                            startActivity(new Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:" + getPackageName())));
                        } catch (Exception e) { /* bỏ qua */ }
                    }
                });
                return "need_overlay";
            }
            if (Build.VERSION.SDK_INT >= 33) {
                try { requestPermissions(new String[] { "android.permission.POST_NOTIFICATIONS" }, 11); } catch (Exception e) { /* bỏ qua */ }
            }
            BubbleService.send(MainActivity.this, BubbleService.ACTION_VISIBLE, visible ? "1" : "0", null, null);
            BubbleService.send(MainActivity.this, BubbleService.ACTION_IDLE, null, null, null);
            return "ok";
        }

        @JavascriptInterface
        public void disable() {
            BubbleService.send(MainActivity.this, BubbleService.ACTION_STOP, null, null, null);
        }

        /** kind: me | nhay | info */
        @JavascriptInterface
        public void show(String small, String big, String kind) {
            BubbleService.send(MainActivity.this, BubbleService.ACTION_SHOW, small, big, kind);
        }

        @JavascriptInterface
        public void idle() {
            BubbleService.send(MainActivity.this, BubbleService.ACTION_IDLE, null, null, null);
        }
    }

    private FrameLayout container;
    private boolean inOverlay = false;
    private boolean visible = true;
    private boolean bubbleOn = false;

    private static String mimeOf(String path) {
        String p = path.toLowerCase();
        if (p.endsWith(".html")) return "text/html";
        if (p.endsWith(".js")) return "text/javascript";
        if (p.endsWith(".wasm")) return "application/wasm";
        if (p.endsWith(".css")) return "text/css";
        if (p.endsWith(".json")) return "application/json";
        return "application/octet-stream";
    }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        getWindow().setStatusBarColor(Color.parseColor("#10162A"));
        getWindow().setNavigationBarColor(Color.parseColor("#10162A"));
        web = new WebView(this);
        web.setBackgroundColor(Color.parseColor("#10162A"));
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setAllowFileAccess(false);
        // Trang app chạy ở địa chỉ https ảo nhưng nối tới game bằng http/ws trong mạng nhà -> cho phép nội dung hỗn hợp
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
        web.setWebViewClient(new WebViewClient() {
            @Override
            public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                Uri u = request.getUrl();
                if (u == null || !HOST.equals(u.getHost())) return super.shouldInterceptRequest(view, request);
                String path = u.getPath();
                if (path == null || path.equals("/")) path = "/index.html";
                path = path.substring(1);
                Map<String, String> headers = new HashMap<>();
                headers.put("Access-Control-Allow-Origin", "*");
                try {
                    InputStream in = getAssets().open(path);
                    return new WebResourceResponse(mimeOf(path), null, 200, "OK", headers, in);
                } catch (Exception e) {
                    return new WebResourceResponse("text/plain", "utf-8", 404, "Not Found", headers, new java.io.ByteArrayInputStream(new byte[0]));
                }
            }
        });
        web.addJavascriptInterface(new BubbleBridge(), "AndroidBubble");
        // giữ trang "sống" khi sang app khác (TikTok...) để vẫn nhận nước đi từ game
        if (Build.VERSION.SDK_INT >= 26) web.setRendererPriorityPolicy(WebView.RENDERER_PRIORITY_IMPORTANT, false);
        web.loadUrl("https://" + HOST + "/index.html");
        container = new FrameLayout(this);
        container.addView(web, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        setContentView(container);
    }

    // Bong bóng chỉ hiện khi app đang ở nền; JS của trang vẫn phải chạy khi ở nền để nhận nước đi từ game.
    @Override
    protected void onResume() {
        super.onResume();
        visible = true;
        if (web != null) web.onResume();
        notifyVisible();
    }

    @Override
    protected void onPause() {
        visible = false;
        if (web != null) web.resumeTimers(); // đừng cho trang ngủ khi sang app khác
        notifyVisible();
        super.onPause();
    }

    private void notifyVisible() {
        try {
            // chỉ báo cho bong bóng nếu nó đang chạy (tránh tự bật khi người dùng chưa cho phép)
            if (BubbleService.running) BubbleService.send(this, BubbleService.ACTION_VISIBLE, visible ? "1" : "0", null, null);
        } catch (Exception e) { /* bỏ qua */ }
    }

    /*
     * GIỮ TRANG SỐNG KHI SANG TIKTOK: Android làm chậm/đóng băng WebView của app đang ở nền, khiến gợi ý chỉ chạy 2-3 lần rồi dừng.
     * Cách chữa: khi app ra nền (và bong bóng đang bật) thì chuyển WebView sang một cửa sổ nổi 1x1 điểm ảnh (vô hình, không chạm được);
     * hệ thống coi đó là trang đang hiển thị nên không làm chậm. Mở lại app thì chuyển WebView về chỗ cũ.
     */
    private WindowManager appWm() {
        return (WindowManager) getApplicationContext().getSystemService(WINDOW_SERVICE);
    }

    private void moveToOverlay() {
        if (inOverlay || web == null || !BubbleService.running) return;
        if (Build.VERSION.SDK_INT >= 23 && !Settings.canDrawOverlays(this)) return;
        try {
            container.removeView(web);
            WindowManager.LayoutParams lp = new WindowManager.LayoutParams(1, 1,
                    Build.VERSION.SDK_INT >= 26 ? WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY : WindowManager.LayoutParams.TYPE_PHONE,
                    WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE | WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE | WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
                    PixelFormat.TRANSLUCENT);
            lp.gravity = android.view.Gravity.TOP | android.view.Gravity.START;
            appWm().addView(web, lp);
            inOverlay = true;
        } catch (Exception e) {
            // không chuyển được thì trả WebView về app như cũ
            try { if (web.getParent() == null) container.addView(web, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT)); } catch (Exception e2) { /* bỏ qua */ }
            inOverlay = false;
        }
    }

    private void moveBack() {
        if (!inOverlay || web == null) return;
        try { appWm().removeView(web); } catch (Exception e) { /* bỏ qua */ }
        inOverlay = false;
        try {
            if (web.getParent() == null) container.addView(web, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        } catch (Exception e) { /* bỏ qua */ }
    }

    @Override
    protected void onStart() {
        super.onStart();
        moveBack();
    }

    @Override
    protected void onStop() {
        if (!isChangingConfigurations()) moveToOverlay();
        super.onStop();
    }

    @Override
    protected void onDestroy() {
        moveBack();
        if (isFinishing() && BubbleService.running) BubbleService.send(this, BubbleService.ACTION_STOP, null, null, null); // app bị vuốt tắt thì bong bóng cũng tắt (hết dữ liệu mới)
        if (web != null) web.destroy();
        super.onDestroy();
    }
}
