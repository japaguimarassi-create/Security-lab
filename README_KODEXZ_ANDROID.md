# Kodexz — Android e Web

Este branch contém o workflow de importação dos arquivos-fonte e compilação do APK.

## Como importar o código real

Envie para a raiz deste branch um ou ambos os arquivos:

- `Kodexz_Android_v6_Source.zip` — projeto Android completo.
- `Kodexz_Kit_v3.zip` — aplicação web, modelo JavaScript e documentação.

[Enviar arquivos para esta branch](https://github.com/japaguimarassi-create/Security-lab/upload/kodexz-android)

Quando um arquivo ZIP for enviado e o commit for confirmado, **GitHub Actions extrairá e fará commit dos arquivos individuais** nas pastas `Kodexz_Android_v6/` e/ou `Kodexz_Kit_v3/`. Não é para o repositório ficar apenas com um transformador de ZIP.

## Compilar o APK

Depois de enviar `Kodexz_Android_v6_Source.zip`, abra [Actions](https://github.com/japaguimarassi-create/Security-lab/actions) e veja a execução **Import Kodexz source files and build Android APK**. Se a compilação terminar com sucesso, baixe o artefato `Kodexz-Android-debug-APK`.

O APK é de depuração, não uma versão assinada para publicar na Google Play.

## Configuração

- Android application ID: `com.kodexz.app`
- Android mínimo: API 26
- Compile SDK: 35
- Java: 17

## Estado importante

Neste momento, o workflow está preparado, mas **os ZIPs enviados na conversa ainda não estão armazenados no GitHub**. A importação não começa até que pelo menos um deles seja enviado ao link acima e confirmado em um commit.

Nunca coloque tokens de acesso ou segredos OAuth diretamente no repositório.
