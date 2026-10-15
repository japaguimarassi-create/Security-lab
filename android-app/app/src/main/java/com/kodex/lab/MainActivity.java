package com.kodex.lab;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.util.Base64;
import android.view.View;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.webkit.ValueCallback;
import android.widget.Toast;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.OutputStream;

public final class MainActivity extends Activity {
    private static final int FILE_CHOOSER_REQUEST_CODE = 2101;
    private static final int CREATE_DOCUMENT_REQUEST_CODE = 2102;
    private static final int MAX_EXPORT_BYTES = 8 * 1024 * 1024;

    private WebView webView;
    private ValueCallback<Uri[]> fileChooserCallback;
    private String pendingExportBase64;
    private String pendingExportFilename;
    private String pendingExportMime;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().setStatusBarColor(Color.rgb(16, 19, 24));
        getWindow().setNavigationBarColor(Color.rgb(16, 19, 24));
        getWindow().getDecorView().setSystemUiVisibility(0);

        webView = new WebView(this);
        webView.setBackgroundColor(Color.rgb(16, 19, 24));
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(true);
        settings.setAllowContentAccess(true);
        settings.setAllowFileAccessFromFileURLs(false);
        settings.setAllowUniversalAccessFromFileURLs(false);
        settings.setSupportZoom(false);
        settings.setBuiltInZoomControls(false);
        settings.setDisplayZoomControls(false);
        settings.setJavaScriptCanOpenWindowsAutomatically(false);
        settings.setSupportMultipleWindows(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setMediaPlaybackRequiresUserGesture(true);
        settings.setUserAgentString(settings.getUserAgentString() + " KodexAndroid/0.4.0");

        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(
                    WebView view,
                    ValueCallback<Uri[]> filePathCallback,
                    FileChooserParams fileChooserParams) {
                if (fileChooserCallback != null) fileChooserCallback.onReceiveValue(null);
                fileChooserCallback = filePathCallback;
                try {
                    startActivityForResult(fileChooserParams.createIntent(), FILE_CHOOSER_REQUEST_CODE);
                    return true;
                } catch (Exception error) {
                    if (fileChooserCallback != null) fileChooserCallback.onReceiveValue(null);
                    fileChooserCallback = null;
                    return false;
                }
            }
        });

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                String scheme = uri.getScheme();
                if ("kodex-download".equalsIgnoreCase(scheme)) {
                    if (request.isForMainFrame()) beginNativeSave();
                    return true;
                }
                if ("file".equalsIgnoreCase(scheme)
                        && uri.toString().startsWith("file:///android_asset/")) {
                    return false;
                }
                if ("https".equalsIgnoreCase(scheme) || "http".equalsIgnoreCase(scheme)) {
                    try {
                        startActivity(new Intent(Intent.ACTION_VIEW, uri));
                    } catch (Exception ignored) {
                    }
                }
                return true;
            }
        });

        setContentView(webView);
        if (savedInstanceState == null) {
            webView.loadUrl("file:///android_asset/index.html");
        } else {
            webView.restoreState(savedInstanceState);
        }
    }

    private void beginNativeSave() {
        if (webView == null) return;
        String script = "(function(){return window.KodexNativePendingDownload ? JSON.stringify(window.KodexNativePendingDownload) : '';})()";
        webView.evaluateJavascript(script, value -> {
            try {
                if (value == null || "null".equals(value)) throw new IllegalStateException("Nenhum arquivo foi preparado.");
                String jsonText = new JSONArray("[" + value + "]").getString(0);
                JSONObject payload = new JSONObject(jsonText);
                pendingExportBase64 = payload.optString("base64", "");
                if (pendingExportBase64.isEmpty() || pendingExportBase64.length() > (MAX_EXPORT_BYTES * 4L / 3L) + 32) {
                    throw new IllegalArgumentException("O conteúdo exportado está vazio ou ultrapassa o limite permitido.");
                }
                byte[] bytes = Base64.decode(pendingExportBase64, Base64.DEFAULT);
                if (bytes.length > MAX_EXPORT_BYTES) throw new IllegalArgumentException("O arquivo ultrapassa 8 MiB.");
                pendingExportFilename = safeFilename(payload.optString("filename", "kodex-export"));
                pendingExportMime = "application/zip".equals(payload.optString("mime"))
                        ? "application/zip" : "text/plain";
                Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT);
                intent.addCategory(Intent.CATEGORY_OPENABLE);
                intent.setType(pendingExportMime);
                intent.putExtra(Intent.EXTRA_TITLE, pendingExportFilename);
                startActivityForResult(intent, CREATE_DOCUMENT_REQUEST_CODE);
            } catch (Exception error) {
                clearPendingExport();
                reportNativeSave(false, "Não foi possível preparar a exportação.");
            }
        });
    }

    private String safeFilename(String filename) {
        String cleaned = filename == null ? "" : filename.replaceAll("[^a-zA-Z0-9._-]", "_");
        if (cleaned.isEmpty() || ".".equals(cleaned) || "..".equals(cleaned)) cleaned = "kodex-export";
        return cleaned.length() > 100 ? cleaned.substring(cleaned.length() - 100) : cleaned;
    }

    private void clearPendingExport() {
        pendingExportBase64 = null;
        pendingExportFilename = null;
        pendingExportMime = null;
    }

    private void reportNativeSave(boolean success, String message) {
        Toast.makeText(this, message, Toast.LENGTH_LONG).show();
        if (webView != null) {
            String script = "if(window.KodexNativeDownloadComplete){window.KodexNativeDownloadComplete("
                    + success + "," + JSONObject.quote(message) + ");}";
            webView.evaluateJavascript(script, null);
        }
    }

    @Override
    @SuppressWarnings("deprecation")
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == FILE_CHOOSER_REQUEST_CODE) {
            if (fileChooserCallback != null) {
                Uri[] results = resultCode == RESULT_OK
                        ? WebChromeClient.FileChooserParams.parseResult(resultCode, data)
                        : null;
                fileChooserCallback.onReceiveValue(results);
                fileChooserCallback = null;
            }
            return;
        }

        if (requestCode == CREATE_DOCUMENT_REQUEST_CODE) {
            if (resultCode != RESULT_OK || data == null || data.getData() == null) {
                clearPendingExport();
                reportNativeSave(false, "Exportação cancelada.");
                return;
            }
            try {
                byte[] bytes = Base64.decode(pendingExportBase64, Base64.DEFAULT);
                if (bytes.length > MAX_EXPORT_BYTES) throw new IllegalArgumentException("O arquivo ultrapassa 8 MiB.");
                try (OutputStream output = getContentResolver().openOutputStream(data.getData())) {
                    if (output == null) throw new IllegalStateException("Não foi possível abrir o destino escolhido.");
                    output.write(bytes);
                    output.flush();
                }
                clearPendingExport();
                reportNativeSave(true, "Arquivo salvo no destino escolhido.");
            } catch (Exception error) {
                clearPendingExport();
                reportNativeSave(false, "Falha ao gravar o arquivo no destino escolhido.");
            }
        }
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        if (webView != null) webView.saveState(outState);
        super.onSaveInstanceState(outState);
    }

    @Override
    public void onBackPressed() {
        if (webView != null && webView.canGoBack()) webView.goBack();
        else super.onBackPressed();
    }

    @Override
    protected void onDestroy() {
        if (fileChooserCallback != null) {
            fileChooserCallback.onReceiveValue(null);
            fileChooserCallback = null;
        }
        if (webView != null) {
            webView.stopLoading();
            webView.loadUrl("about:blank");
            webView.destroy();
            webView = null;
        }
        super.onDestroy();
    }
}
