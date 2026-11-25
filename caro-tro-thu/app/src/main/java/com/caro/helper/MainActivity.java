package com.caro.helper;

import android.app.Activity;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.view.WindowManager;
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
        web.loadUrl("https://" + HOST + "/index.html");
        setContentView(web);
    }

    @Override
    protected void onDestroy() {
        if (web != null) web.destroy();
        super.onDestroy();
    }
}
