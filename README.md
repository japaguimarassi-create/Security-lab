# BlocoVivo — Forge 1.7.10

Mod para Minecraft Java 1.7.10 com Forge 10.13.4.1614. O botão Stevebô no menu principal abre uma seleção de destino e inicia o fluxo normal de criação de mundo integrado. O Stevebô é criado no destino selecionado; placas no ponto inicial permitem viajar entre Mundo comum, Arena PvP, Sobrevivência, Construção e Exploração.

## Recursos

- Botão no menu principal e tela de seleção antes de criar um mundo.
- Entidade autônoma chamada Stevebô, com caminhada, observação, navegação, seguimento e combate iniciado por comando.
- Comandos no chat: !stevebo ajuda, vem, siga, pare, proteja, pvp e status. Perguntas sobre Minecraft são respondidas pela base local e pelo recuperador semântico.
- Pipeline de treinamento de um modelo de embeddings com exatamente 250.000 pesos (500 × 500). O modelo é treinado durante a compilação com o corpus versionado em data/minecraft_corpus.txt e empacotado no JAR.
- GitHub Actions tenta compilar até três vezes e publica o JAR como artefato quando o build passa.

## Mapas e servidor

O botão cria um mundo single-player com servidor integrado do Minecraft. Os destinos são regiões preparadas dentro desse mundo, não cinco geradores de terreno independentes. Para entrar em um servidor dedicado remoto, o servidor também precisa ter o mod instalado.

## Skin

O renderizador procura a textura em src/main/resources/assets/stevebo/textures/entity/stevebo.png. A textura atual é uma aproximação provisória; a correspondência exata com a skin usada pelo TheLuics ainda precisa ser validada.

Uma página pública intitulada Stevebô foi encontrada no NovaSkin, mas não foi possível confirmar que seja a mesma skin do TheLuics: https://minecraft.novaskin.me/post/9lkmutvba9/steveb

## Compilação

Ambiente recomendado: JDK 8, Gradle 4.5 e Python 3 com NumPy e Pillow. O fluxo do GitHub instala as dependências, treina o modelo e executa Gradle. O resultado esperado é build/libs/BlocoVivo-0.1.0.jar.

Localmente, instale NumPy com pip e execute python3 scripts/train_model.py antes de gradle clean build.

## Limites da IA

Os 250.000 parâmetros são pesos treináveis de embeddings semânticos; eles não equivalem a um modelo generativo grande. O corpus inicial aborda crafting, sobrevivência, mineração, combate, mobs, redstone, dimensões e mecânicas comuns, mas não contém literalmente todas as informações de Minecraft. O controle de movimento e os comandos são determinísticos para evitar que uma resposta de linguagem tente executar ações inseguras ou inválidas.

## Referências

- Forge 1.7.10: https://files.minecraftforge.net/net/minecraftforge/forge/index_1.7.10.html
- ForgeGradle 1.2 compatibility fork: https://github.com/anatawa12/ForgeGradle-1.2
