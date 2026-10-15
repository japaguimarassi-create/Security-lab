# Kodexz / Security Lab

O branch `kodexz-android` contém a automação para importar os fontes do Kodexz e compilar o APK no GitHub Actions.

## Arquivos-fonte necessários

- [Kodexz Android v6 — projeto Android](https://sandbox:/mnt/data/Kodexz_Android_v6_Source.zip)
- [Kodexz Kit v3 — aplicação web](https://sandbox:/mnt/data/Kodexz_Kit_v3.zip)

Os links acima são anexos desta conversa e **não ficam automaticamente disponíveis no GitHub**. Para enviar os fontes ao repositório, baixe o ZIP correspondente e faça upload para a raiz da branch `kodexz-android):

[Enviar ZIPs para o branch](https://github.com/japaguimarassi-create/Security-lab/upload/kodexz-android)

## O que acontece depois do upload

O workflow em [GitHub Actions](https://github.com/japaguimarassi-create/Security-lab/actions) extrai os ZIPs e comita os arquivos reais para:

- `Kodexz_Android_v6/` — projeto Android com código Java, interface web, assets e configuração Gradle.
- `Kodexz_Kit_v3/` — aplicação web, modelo JavaScript e documentação.

Se o arquivo Android estiver presente, o workflow também compila um APK de depuração e publica o artefato `Kodexz-Android-debug-APK`.

**Estado atual:** a automação foi configurada, mas os ZIPs ainda precisam ser enviados ao GitHub. Portanto, os diretórios de código ainda não foram criados no branch.
