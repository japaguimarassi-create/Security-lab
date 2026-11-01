package dev.klod;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

public final class KlodClient {
    private final String baseUrl;
    private final String apiKey;

    public KlodClient(String baseUrl, String apiKey) {
        this.baseUrl = baseUrl.replaceAll("/+$", "");
        this.apiKey = apiKey;
    }

    public String chat(String jsonBody) throws IOException {
        HttpURLConnection connection = (HttpURLConnection) new URL(
            baseUrl + "/v1/chat/completions").openConnection();
        connection.setRequestMethod("POST");
        connection.setConnectTimeout(10000);
        connection.setReadTimeout(120000);
        connection.setDoOutput(true);
        connection.setRequestProperty("Content-Type", "application/json; charset=utf-8");
        connection.setRequestProperty("X-API-Key", apiKey);
        byte[] body = jsonBody.getBytes(StandardCharsets.UTF_8);
        connection.setFixedLengthStreamingMode(body.length);
        try {
            try (OutputStream output = connection.getOutputStream()) {
                output.write(body);
            }
            int status = connection.getResponseCode();
            InputStream stream = status >= 200 && status < 300
                ? connection.getInputStream() : connection.getErrorStream();
            ByteArrayOutputStream buffer = new ByteArrayOutputStream();
            byte[] chunk = new byte[4096];
            int read;
            while ((read = stream.read(chunk)) != -1) buffer.write(chunk, 0, read);
            String response = new String(buffer.toByteArray(), StandardCharsets.UTF_8);
            if (status < 200 || status >= 300) {
                throw new IOException("Klod API HTTP " + status + ": " + response);
            }
            return response;
        } finally {
            connection.disconnect();
        }
    }
}
