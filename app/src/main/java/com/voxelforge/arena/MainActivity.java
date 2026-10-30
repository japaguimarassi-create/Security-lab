package com.voxelforge.arena;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Bundle;
import android.speech.RecognitionListener;
import android.speech.RecognizerIntent;
import android.speech.SpeechRecognizer;
import android.view.View;
import android.view.Window;
import android.view.WindowManager;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Locale;

public final class MainActivity extends Activity {
    private static final int REQUEST_MICROPHONE = 4102;
    private WebView webView;
    private SpeechRecognizer recognizer;
    private boolean permissionPending;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        Window window = getWindow();
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        window.getDecorView().setSystemUiVisibility(
            View.SYSTEM_UI_FLAG_FULLSCREEN
                | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                | View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
        );

        webView = new WebView(this);
        webView.setBackgroundColor(0xFF080D15);
        webView.setOverScrollMode(View.OVER_SCROLL_NEVER);
        webView.setWebChromeClient(new WebChromeClient());
        webView.setWebViewClient(new WebViewClient());
        webView.getSettings().setJavaScriptEnabled(true);
        webView.getSettings().setDomStorageEnabled(true);
        webView.getSettings().setAllowFileAccess(true);
        webView.getSettings().setAllowContentAccess(false);
        webView.getSettings().setMediaPlaybackRequiresUserGesture(false);
        webView.addJavascriptInterface(new VoiceBridge(), "AndroidBridge");
        setContentView(webView);
        webView.loadUrl("file:///android_asset/game/index.html");
    }

    private final class VoiceBridge {
        @JavascriptInterface
        public void startVoice() {
            runOnUiThread(() -> {
                if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
                    permissionPending = true;
                    requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, REQUEST_MICROPHONE);
                    return;
                }
                beginRecognition();
            });
        }

        @JavascriptInterface
        public String platformName() {
            return "Android SpeechRecognizer";
        }
    }

    private void beginRecognition() {
        if (!SpeechRecognizer.isRecognitionAvailable(this)) {
            sendVoiceError("O serviço de reconhecimento de voz não está disponível neste Android.");
            return;
        }
        try {
            if (recognizer != null) {
                recognizer.destroy();
            }
            recognizer = SpeechRecognizer.createSpeechRecognizer(this);
            recognizer.setRecognitionListener(new RecognitionListener() {
                @Override public void onReadyForSpeech(Bundle params) { sendVoiceStatus("Ouvindo… fale agora."); }
                @Override public void onBeginningOfSpeech() { sendVoiceStatus("Capturando sua frase…"); }
                @Override public void onRmsChanged(float rmsdB) { }
                @Override public void onBufferReceived(byte[] buffer) { }
                @Override public void onEndOfSpeech() { sendVoiceStatus("Interpretando voz…"); }
                @Override public void onError(int error) { sendVoiceError(errorMessage(error)); }
                @Override public void onResults(Bundle results) {
                    ArrayList<String> matches = results.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION);
                    if (matches != null && !matches.isEmpty()) {
                        String text = matches.get(0);
                        webView.evaluateJavascript("window.onNativeSpeechResult && window.onNativeSpeechResult(" + JSONObject.quote(text) + ")", null);
                    } else {
                        sendVoiceError("Não consegui reconhecer a frase. Tente novamente ou digite o comando.");
                    }
                }
                @Override public void onPartialResults(Bundle partialResults) {
                    ArrayList<String> matches = partialResults.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION);
                    if (matches != null && !matches.isEmpty()) {
                        String text = matches.get(0);
                        webView.evaluateJavascript("window.onNativeSpeechPartial && window.onNativeSpeechPartial(" + JSONObject.quote(text) + ")", null);
                    }
                }
                @Override public void onEvent(int eventType, Bundle params) { }
            });

            Intent intent = new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH);
            intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM);
            intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE, "pt-BR");
            intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_PREFERENCE, "pt-BR");
            intent.putExtra(RecognizerIntent.EXTRA_ONLY_RETURN_LANGUAGE_PREFERENCE, false);
            intent.putExtra(RecognizerIntent.EXTRA_PREFER_OFFLINE, true);
            intent.putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true);
            intent.putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 3);
            recognizer.startListening(intent);
        } catch (Exception error) {
            sendVoiceError("Falha ao iniciar o microfone: " + error.getClass().getSimpleName());
        }
    }

    private String errorMessage(int error) {
        switch (error) {
            case SpeechRecognizer.ERROR_AUDIO: return "Falha no áudio. Verifique o microfone.";
            case SpeechRecognizer.ERROR_CLIENT: return "O reconhecimento foi interrompido. Tente novamente.";
            case SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS: return "Permissão de microfone não concedida.";
            case SpeechRecognizer.ERROR_NETWORK:
            case SpeechRecognizer.ERROR_NETWORK_TIMEOUT: return "O serviço de voz falhou. Confira se há pacote offline de português instalado ou use o campo de texto.";
            case SpeechRecognizer.ERROR_NO_MATCH: return "Não entendi a frase. Fale mais perto do microfone ou digite o comando.";
            case SpeechRecognizer.ERROR_RECOGNIZER_BUSY: return "O reconhecimento já está ocupado. Aguarde um instante.";
            case SpeechRecognizer.ERROR_SPEECH_TIMEOUT: return "Não detectei fala. Tente novamente.";
            default: return "Erro de reconhecimento (" + error + "). Você também pode digitar o comando.";
        }
    }

    private void sendVoiceStatus(String message) {
        webView.evaluateJavascript("window.onNativeSpeechStatus && window.onNativeSpeechStatus(" + JSONObject.quote(message) + ")", null);
    }

    private void sendVoiceError(String message) {
        webView.evaluateJavascript("window.onNativeSpeechError && window.onNativeSpeechError(" + JSONObject.quote(message) + ")", null);
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == REQUEST_MICROPHONE && permissionPending) {
            permissionPending = false;
            if (grantResults.length > 0 && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
                beginRecognition();
            } else {
                sendVoiceError("Permita o acesso ao microfone para usar comandos por voz. O modo de texto continua disponível.");
            }
        }
    }

    @Override
    public void onBackPressed() {
        webView.evaluateJavascript("window.showPauseMenu && window.showPauseMenu()", null);
    }

    @Override
    protected void onDestroy() {
        if (recognizer != null) {
            recognizer.cancel();
            recognizer.destroy();
            recognizer = null;
        }
        if (webView != null) {
            webView.removeJavascriptInterface("AndroidBridge");
            webView.destroy();
        }
        super.onDestroy();
    }
}
