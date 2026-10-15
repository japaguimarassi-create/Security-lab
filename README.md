# Kodexz / Security Lab

O branch `kodexz-android` contém a automação para importar os fontes do Kodexz e compilar o APK no GitHub Actions.

## Arquivos-fonte necessários

Envie um ou ambos os arquivos ZIP para a raiz deste branch:

- `Kodexz_Android_v6_Source.zip` — projeto Android, incluindo código Java, interface, assets e Gradle.
- `Kodexz_Kit_v3.zip` — aplicação web, modelo JavaScript e documentação.

[Enviar os ZIPs para esta branch](https://github.com/japaguimarassi-create/Security-lab/upload/kodexz-android)

> Os ZIPs anexados nesta conversa não são transferidos automaticamente para o GitHub. É necessário baixá-los para o dispositivo e enviar os arquivos pelo link acima.

## O que acontece depois do upload

O workflow em [GitHub Actions](https://github.com/japaguimarassi-create/Security-lab/actions) extrai os arquivos e cria os diretórios de código:

- `Kodexz_Android_v6/` — projeto Android.
- `Kodexz_Kit_v3/` — aplicação web e documentação.

Se `Kodexz_Android_v6_Source.zip` estiver presente, o workflow também compila um APK de depuração e publica o artefato `Kodexz-Android-debug-APK`.

**Estado atual:** a automação está configurada, mas os ZIPs ainda precisam ser enviados ao GitHub. Os diretórios de fonte ainda não foram criados no branch.
