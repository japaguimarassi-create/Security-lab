# Kodexz Android v6 — fonte principal

Este branch prepara a importação e compilação de **Kodexz Android v6.0.0**. Esta é a versão Android canônica. `Kodexz_Kit_v3` é um pacote web separado; o número 3 não é uma versão Android concorrente.

## Fonte esperada

Envie à raiz deste branch o arquivo `Kodexz_Android_v6_Source.zip`, que deve conter `Kodexz_Android_v6/` com o projeto Gradle, código Java, interface HTML, integração nativa e modelo `model.js`.

[Enviar o ZIP Android v6 para esta branch](https://github.com/japaguimarassi-create/Security-lab/upload/kodexz-android)

O ZIP anexado à conversa não é transferido automaticamente ao GitHub. Baixe o arquivo, envie-o pelo link e confirme o commit.

## Fluxo automático

Ao detectar o ZIP, GitHub Actions irá:

1. validar os arquivos Android essenciais e as versões `versionCode 6` / `versionName '6.0.0'`;
2. executar `tools-check.sh` para validar JavaScript, HTML, XML, IDs e modelo;
3. extrair e comitar os arquivos individuais na pasta `Kodexz_Android_v6/`;
4. remover o ZIP enviado do histórico atual do branch para que o repositório fique com o código-fonte, não só com o arquivo compactado;
5. compilar o APK de depuração e publicar o artefato `Kodexz-Android-v6-debug-APK`, se o build for bem-sucedido.

Depois da importação, é possível iniciar novas compilações pelo botão **Run workflow**, sem reenviar o ZIP.

[Ver execuções e baixar o artefato](https://github.com/japaguimarassi-create/Security-lab/actions)

## Estado real

Até o ZIP ser enviado, este branch contém a automação e esta documentação, **não** o projeto completo. A fonte foi auditada localmente, e verificações estáticas passaram, mas ainda não existe um APK validado porque o ZIP ainda não foi compilado no runner Android.

O APK será assinado para depuração e instalação manual; não é uma versão de release assinada para Google Play. Não coloque Client Secrets, tokens pessoais ou outras credenciais no repositório.
