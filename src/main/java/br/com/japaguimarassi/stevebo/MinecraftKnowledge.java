package br.com.japaguimarassi.stevebo;

public final class MinecraftKnowledge {
    public static final String[] PROMPTS = {
        "diamante mineracao", "ferro mineracao", "carvao tocha", "bancada crafting",
        "fornalha cozinhar", "comida fome", "cama respawn", "armadura protecao",
        "encantamento experiencia", "pocao alquimia", "nether obsidiana", "ender dragon",
        "redstone circuito", "pistao slime", "aldeao trocas", "creeper explosao",
        "zumbi combate", "esqueleto arco", "pvp combate", "arco flecha",
        "ataque critico", "queda agua", "cavalo sela", "bioma exploracao",
        "plantar trigo", "ferrovia minecart", "forja mod forge", "servidor integrado",
        "lobo domesticar", "pescaria", "tocha mineracao", "encantamento reparacao"
    };

    public static final String[] ANSWERS = {
        "No Minecraft 1.7.10, procure diamantes nas camadas baixas. A faixa por volta de Y 5–12 é comum; minerar perto de Y 11 ajuda a evitar muitos lagos de lava.",
        "O ferro aparece em várias alturas, inclusive em cavernas e encostas. Leve tochas e uma picareta de pedra ou melhor.",
        "Carvão aparece em grandes quantidades em cavernas e montanhas. Transforme-o em tochas para iluminar a mina e reduzir o surgimento de mobs hostis.",
        "A bancada de trabalho é feita com quatro tábuas de madeira em um quadrado 2×2 no inventário. Ela permite receitas que exigem uma grade 3×3.",
        "A fornalha é feita com oito pedregulhos ao redor do espaço central da bancada. Use combustível para fundir minérios e cozinhar alimentos.",
        "Comida recupera a barra de fome e, com fome suficiente, ajuda a regenerar vida. Carne cozida costuma ser uma opção eficiente no início.",
        "Uma cama é feita com três blocos de lã e três tábuas na linha inferior. Dormir define o ponto de renascimento, desde que o local continue válido.",
        "Armaduras reduzem dano. No início, faça armadura de ferro quando tiver recursos; leve também comida, escudo não existe na versão 1.7.10, e uma espada.",
        "A mesa de encantamentos usa obsidiana, diamantes e um livro. Estantes próximas aumentam os níveis disponíveis; gaste níveis com equipamentos que pretende manter.",
        "Para poções, use um suporte de poções, pó de blaze como combustível e verruga do Nether como base de muitas receitas. Combine ingredientes conforme o efeito desejado.",
        "O portal do Nether é montado com obsidiana em uma moldura de pelo menos 4×5 blocos externos e ativado com fogo. Leve comida e equipamento resistente.",
        "O Dragão do End fica na dimensão The End. Destrua os cristais de cura nas torres com cuidado e prepare arco, blocos, armadura e bastante comida.",
        "Redstone transmite sinais e permite circuitos. Alavancas, botões, placas de pressão, repetidores e comparadores ajudam a controlar portas e mecanismos.",
        "Pistões movem blocos e pistões grudentos podem puxar blocos de volta. Slimeballs são úteis para mecanismos que precisam grudar blocos.",
        "Aldeões podem trocar itens por esmeraldas e vice-versa. As ofertas dependem da profissão e podem mudar conforme as trocas são realizadas.",
        "Creepers explodem perto do jogador. Afaste-se assim que ouvir o chiado, use arco à distância ou ataque e recue antes da explosão.",
        "Zumbis são hostis e podem aparecer em áreas escuras. Ilumine construções e cavernas, lute com espaço para recuar e evite ficar cercado.",
        "Esqueletos atacam de longe com arcos. Use cobertura, aproxime-se em zigue-zague ou devolva o ataque com arco.",
        "No PvP da 1.7.10, controle a distância, varie o movimento lateral, observe o alcance da espada e leve comida e armadura. O tempo de ataque difere das versões modernas.",
        "O arco consome flechas e é útil para iniciar combate à distância. Segure o botão para puxá-lo antes de soltar a flecha.",
        "Um ataque crítico normalmente acontece ao acertar durante a queda de um salto, desde que as condições do jogo permitam. Não salte sem pensar se isso entregar sua posição.",
        "Um balde de água pode ajudar a reduzir dano de queda se for colocado corretamente antes do impacto. Treine em local seguro para dominar o tempo.",
        "Para montar um cavalo domesticado, use uma sela. A sela não é fabricada normalmente na versão 1.7.10; procure em baús ou negociações apropriadas.",
        "Biomas têm terreno, clima e recursos diferentes. Use marcos, mapas, coordenadas e comida para evitar se perder longe da base.",
        "Plante sementes em terra arada junto de água e mantenha luz suficiente. Colha trigo maduro e reponha sementes para continuar a plantação.",
        "Trilhos e carrinhos facilitam o transporte. Trilhos energizados precisam de redstone e servem para manter carrinhos em movimento.",
        "Forge 1.7.10 usa mods compilados para Java 7/8 e a API Forge correspondente. Não misture jars de Fabric ou versões modernas do Forge.",
        "O mundo criado pelo botão Stevebô é um mundo integrado local: o servidor roda dentro do próprio Minecraft. Um servidor dedicado remoto precisa instalar o mesmo mod.",
        "Dê ossos a lobos até domesticá-los. Lobos domesticados podem acompanhar e defender o jogador, mas podem se ferir em combate.",
        "Use uma vara de pesca perto da água e recolha a linha quando houver mordida. A pesca pode render comida e itens variados.",
        "Coloque tochas em intervalos regulares em minas e cavernas. Isso melhora a visibilidade e reduz a ocorrência de mobs hostis em áreas iluminadas.",
        "A bigorna combina, renomeia e repara itens mediante experiência e materiais. Algumas combinações custam mais níveis conforme o histórico do item."
    };

    private MinecraftKnowledge() {
    }

    public static String answerForKeywords(String text) {
        String q = java.text.Normalizer.normalize(text == null ? "" : text.toLowerCase(java.util.Locale.ROOT), java.text.Normalizer.Form.NFD).replaceAll("\\p{M}", "");
        if (has(q, "diamante", "diamond")) return ANSWERS[0];
        if (has(q, "ferro", "iron")) return ANSWERS[1];
        if (has(q, "carvao", "tocha", "torch")) return ANSWERS[2];
        if (has(q, "bancada", "crafting", "mesa de trabalho")) return ANSWERS[3];
        if (has(q, "fornalha", "cozinhar", "fundir")) return ANSWERS[4];
        if (has(q, "comida", "fome", "food")) return ANSWERS[5];
        if (has(q, "cama", "respawn", "renascer")) return ANSWERS[6];
        if (has(q, "armadura", "protecao")) return ANSWERS[7];
        if (has(q, "encantamento", "estante", "mesa de encantamento")) return ANSWERS[8];
        if (has(q, "pocao", "alquimia")) return ANSWERS[9];
        if (has(q, "nether", "portal")) return ANSWERS[10];
        if (has(q, "dragao", "the end", "ender")) return ANSWERS[11];
        if (has(q, "redstone", "circuito")) return ANSWERS[12];
        if (has(q, "pistao", "slime")) return ANSWERS[13];
        if (has(q, "aldeao", "villager", "troca")) return ANSWERS[14];
        if (has(q, "creeper")) return ANSWERS[15];
        if (has(q, "zumbi", "zombie")) return ANSWERS[16];
        if (has(q, "esqueleto", "skeleton")) return ANSWERS[17];
        if (has(q, "pvp", "jogador contra jogador")) return ANSWERS[18];
        if (has(q, "arco", "flecha")) return ANSWERS[19];
        if (has(q, "critico", "pulo", "salto")) return ANSWERS[20];
        if (has(q, "queda", "agua", "fall")) return ANSWERS[21];
        if (has(q, "cavalo", "sela")) return ANSWERS[22];
        if (has(q, "bioma", "explorar", "exploracao")) return ANSWERS[23];
        if (has(q, "trigo", "plantar", "fazenda", "farm")) return ANSWERS[24];
        if (has(q, "trilho", "carrinho", "minecart")) return ANSWERS[25];
        if (has(q, "forge", "mod")) return ANSWERS[26];
        if (has(q, "servidor", "mundo integrado")) return ANSWERS[27];
        if (has(q, "lobo", "domesticar")) return ANSWERS[28];
        if (has(q, "pesca", "pescar")) return ANSWERS[29];
        if (has(q, "bigorna", "reparar", "reparacao")) return ANSWERS[31];
        return null;
    }

    private static boolean has(String text, String... values) {
        for (String value : values) if (text.contains(value)) return true;
        return false;
    }
}