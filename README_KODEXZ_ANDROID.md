# Kodexz Android v6 — fonte principal

Este branch prepara a importação e compilação de **Kodexz Android v6.0.0**. O pacote Android v6 é a versão principal selecionada após a auditoria; o nome `Kodexz_Kit_v3` identifica outro pacote web e não define a versão do app Android.

## Arquivo-fonte esperado

Envie para a raiz deste branch o arquivo `Kodexz_Android_v6_Source.zip`. Ele deve conter o diretório `Kodexz_Android_v6/`, com pelo menos:

- `app/src/main/java/com/kodexz/app/MainActivity.java`
- `app/src/main/assets/public/index.html`
- `app/src/main/assets/public/model.js`
- `app/build.gradle`

[Enviar o ZIP Android v6 para esta branch](https://github.com/japaguimarassi-create/Security-lab/upload/kodexz-android)

O anexo da conversa não é enviado automaticamente ao GitHub. Baixe o ZIP e faça o upload pelo link acima; depois confirme o commit.

## Fluxo depois do upload

1. GitHub Actions verifica se os arquivos essenciais existem e se a configuração declara `versionCode 6` e `versionName '6.0.0'`.
2. O workflow extrai e confirma os arquivos individuais na pasta versionada `Kodexz_Android_v6/`.
3. Executa verificações estáticas de JavaScript e estrutura.
4. Instala Java 17, Android SDK 35 e Gradle 8.10.2 e tenta compilar o APK de depuração.
5. Se o build terminar com sucesso, publica o artefato `Kodexz-Android-v6-debug-APK` por 14 dias.

[Ver execuções e baixar o artefato](https://github.com/japaguimarassi-create/Security-lab/actions)

## Estado real

Até o ZIP ser enviado pelo link acima, o branch contém a automação e a documentação, **não** o projeto-fonte completo. Ainda não há APK validado. Não interprete uma execução configurada ou um ZIP de fontes como prova de compilação.

O APK gerado será de depuração, adequado para teste e instalação manual. Ele não será uma versão assinada para publicação na Google Play. Não coloque Client Secrets, tokens pessoais ou outros segredos no repositório.
