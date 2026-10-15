(() => {
  "use strict";

  const api = () => window.KodexWorkspaceAPI;
  const panel = document.getElementById("terminal-panel");
  const output = document.getElementById("terminal-output");
  const form = document.getElementById("terminal-form");
  const input = document.getElementById("terminal-input");
  const promptLabel = document.getElementById("terminal-prompt");
  const HISTORY_KEY = "kodex:terminal-history:v1";
  const MAX_HISTORY = 100;
  const MAX_OUTPUT = 700;
  let cwd = "";
  let history = loadHistory();
  let historyIndex = history.length;

  function loadHistory() {
    try {
      const raw = JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]");
      return Array.isArray(raw) ? raw.filter(value => typeof value === "string").slice(-MAX_HISTORY) : [];
    } catch {
      return [];
    }
  }

  function saveHistory() {
    try {
      localStorage.setItem(HISTORY_KEY, JSON.stringify(history.slice(-MAX_HISTORY)));
    } catch {
      return;
    }
  }

  function writeLine(text, kind = "") {
    const line = document.createElement("div");
    line.className = "terminal-entry" + (kind ? " " + kind : "");
    line.textContent = String(text ?? "");
    output.append(line);
    while (output.children.length > MAX_OUTPUT) output.firstElementChild.remove();
    output.scrollTop = output.scrollHeight;
  }

  function writeBlock(text, kind = "") {
    const value = String(text ?? "");
    const lines = value.split("\n");
    for (const line of lines) writeLine(line, kind);
  }

  function setPrompt() {
    promptLabel.textContent = "~" + (cwd ? "/" + cwd : "") + " $";
    document.getElementById("toggle-terminal").setAttribute("aria-expanded", String(!panel.hidden));
  }

  function tokenize(source) {
    const tokens = [];
    let current = "";
    let quote = "";
    let escaped = false;
    let tokenStarted = false;
    for (const char of String(source)) {
      if (escaped) {
        current += char;
        escaped = false;
        tokenStarted = true;
        continue;
      }
      if (char === "\\" && quote !== "'") {
        escaped = true;
        tokenStarted = true;
        continue;
      }
      if (quote) {
        if (char === quote) quote = "";
        else current += char;
        tokenStarted = true;
        continue;
      }
      if (char === "'" || char === '"') {
        quote = char;
        tokenStarted = true;
        continue;
      }
      if (char === ">") {
        if (tokenStarted) tokens.push(current);
        tokens.push(">");
        current = "";
        tokenStarted = false;
        continue;
      }
      if (/\s/.test(char)) {
        if (tokenStarted) tokens.push(current);
        current = "";
        tokenStarted = false;
        continue;
      }
      current += char;
      tokenStarted = true;
    }
    if (escaped) current += "\\";
    if (quote) throw new Error("Aspas não foram fechadas.");
    if (tokenStarted) tokens.push(current);
    return tokens;
  }

  function resolvePath(rawPath) {
    const source = String(rawPath ?? "").trim();
    if (!source || source.startsWith("/") || /^[a-z]:/i.test(source)) {
      throw new Error("Use caminhos relativos ao workspace, sem caminhos absolutos.");
    }
    const parts = cwd ? cwd.split("/") : [];
    for (const part of source.replace(/\\/g, "/").split("/")) {
      if (!part || part === ".") continue;
      if (part === "..") {
        if (!parts.length) throw new Error("O caminho não pode sair da raiz do projeto.");
        parts.pop();
        continue;
      }
      parts.push(part);
    }
    if (!parts.length) throw new Error("O caminho aponta para a raiz; informe um arquivo ou diretório.");
    return api().getDirectories().length >= 0
      ? window.KodexWorkspaceEngine.normalizeProjectPath(parts.join("/"))
      : parts.join("/");
  }

  function resolveDirectory(rawPath) {
    const source = String(rawPath ?? "").trim();
    if (!source || source === "." || source === "~" || source === "/") return "";
    if (source.startsWith("/") || /^[a-z]:/i.test(source)) throw new Error("Use diretórios relativos ao workspace.");
    const parts = cwd ? cwd.split("/") : [];
    for (const part of source.replace(/\\/g, "/").split("/")) {
      if (!part || part === ".") continue;
      if (part === "..") {
        if (!parts.length) throw new Error("Não é permitido sair da raiz do projeto.");
        parts.pop();
      } else {
        parts.push(part);
      }
    }
    return parts.join("/");
  }

  function fileEntry(path) {
    return api().getFiles().find(file => file.path === path) || null;
  }

  function ensureDirectory(path) {
    if (!path) return;
    if (!api().getDirectories().includes(path)) throw new Error("Diretório não encontrado: " + path);
  }

  function requireArgs(args, count, usage) {
    if (args.length < count) throw new Error("Uso: " + usage);
  }

  function showHelp() {
    writeBlock([
      "Comandos disponíveis neste terminal de projeto:",
      "  help                               lista os comandos",
      "  pwd                                mostra a pasta atual",
      "  ls [pasta]                         lista arquivos e pastas",
      "  tree [pasta]                       mostra a árvore até 6 níveis",
      "  cd <pasta|..|/>                    muda a pasta virtual",
      "  cat <arquivo>                      exibe um arquivo de texto",
      "  head <arquivo> [linhas]             exibe o início de um arquivo",
      "  tail <arquivo> [linhas]             exibe o fim de um arquivo",
      "  wc <arquivo>                       conta linhas, palavras e bytes",
      "  stat <arquivo>                     mostra metadados locais",
      "  touch <arquivo>                    cria um arquivo vazio",
      "  mkdir <pasta>                      cria uma pasta virtual",
      "  rmdir <pasta>                      remove uma pasta vazia",
      "  write <arquivo> <texto>             substitui o conteúdo",
      "  append <arquivo> <texto>            acrescenta ao fim",
      "  echo <texto> > <arquivo>            grava texto com redirecionamento",
      "  mv <origem> <destino>              renomeia/move dentro do projeto",
      "  rm <arquivo>                       exclui após confirmação",
      "  grep <texto> [arquivo|pasta]        busca texto literal",
      "  find [pasta] [parte-do-nome]        encontra caminhos",
      "  check                              faz checagens estáticas",
      "  preview                            abre a prévia HTML isolada",
      "  zip                                exporta o projeto em ZIP",
      "  ai info                            mostra o perfil do modelo de treino",
      "  ai queue [1..1000000]              gera um plano local de experimentos",
      "  ai status                          lê o plano local de treino, se existir",
      "  history                            lista comandos anteriores",
      "  clear                              limpa a saída do terminal",
      "",
      "Não é Bash: não executa comandos do Android, não instala pacotes e não finge ter compilado código."
    ].join("\n"), "info");
  }

  function listDirectory(path, indent = "") {
    const entries = api().list(path);
    if (!entries.length) {
      writeLine(indent + "(pasta vazia)", "muted");
      return;
    }
    for (const entry of entries) {
      writeLine(indent + entry.name + (entry.type === "directory" ? "/" : "  [" + entry.bytes + " B]"), entry.type === "directory" ? "info" : "");
    }
  }

  function buildTree(path, depth = 0, prefix = "") {
    if (depth > 6) {
      writeLine(prefix + "… (limite de profundidade)", "muted");
      return;
    }
    const entries = api().list(path);
    entries.forEach((entry, index) => {
      const last = index === entries.length - 1;
      writeLine(prefix + (last ? "└── " : "├── ") + entry.name + (entry.type === "directory" ? "/" : ""), entry.type === "directory" ? "info" : "");
      if (entry.type === "directory") buildTree(path ? path + "/" + entry.name : entry.name, depth + 1, prefix + (last ? "    " : "│   "));
    });
  }

  function matchingFiles(target) {
    const all = api().getFiles();
    if (!target || target === ".") return all;
    let path;
    try {
      path = resolvePath(target);
    } catch {
      path = resolveDirectory(target);
    }
    const direct = all.filter(file => file.path === path);
    if (direct.length) return direct;
    return all.filter(file => file.path.startsWith(path + "/"));
  }

  function runCheck() {
    const report = api().check();
    writeLine("Análise estática: " + report.passed + " aprovado(s), " + report.warnings + " aviso(s), " + report.failed + " falha(s).", report.failed ? "error" : report.warnings ? "warn" : "success");
    for (const item of report.checks) {
      const mark = item.status === "pass" ? "✓" : item.status === "warn" ? "!" : "×";
      const kind = item.status === "pass" ? "success" : item.status === "warn" ? "warn" : "error";
      writeLine(mark + " " + item.title + " — " + item.detail, kind);
    }
    writeLine("Isso não executou o programa nem substitui testes ou compilação.", "muted");
  }

  function handleAi(args) {
    const action = args[0] || "info";
    if (action === "info") {
      writeBlock([
        "Kodex Transformer 0.5 — perfil do sistema de treinamento",
        "Arquitetura: decoder-only causal Transformer",
        "Parâmetros treináveis: 875.777",
        "Tokenizer: bytes UTF-8 (0–255) + EOS (256)",
        "Embedding: 128 · cabeças de atenção: 4 · blocos: 4 · FFN: 512 · contexto: 128",
        "Treinamento: PyTorch, do zero, AdamW, clipping de gradiente, validação separada e checkpoints",
        "O modelo de 875.777 parâmetros é um experimento separado; não foi conectado ao chat nem convertido para APK."
      ].join("\n"), "info");
      return;
    }
    if (action === "queue") {
      const count = args[1] === undefined ? 1000000 : Number(args[1]);
      if (!Number.isSafeInteger(count) || count < 1 || count > 1000000) throw new Error("Use um número inteiro entre 1 e 1.000.000.");
      const plan = {
        schemaVersion: 1,
        system: "Kodex concurrent training sweep",
        logicalTrials: count,
        workers: Math.max(1, Math.min(4, navigator.hardwareConcurrency || 2)),
        stepsPerTrial: 100,
        modelParameters: 875777,
        createdAt: new Date().toISOString(),
        status: "planned-not-executed",
        note: "Esta é apenas a configuração. O terminal do workspace não inicia Python nem GitHub Actions."
      };
      const result = api().write("training/sweep-request.json", JSON.stringify(plan, null, 2) + "\n");
      writeLine("Plano salvo em " + result.path + " (" + count.toLocaleString("pt-BR") + " experimentos lógicos).", "success");
      writeLine("Nenhum treinamento foi iniciado. Exporte o projeto e execute training/run_sweep.py em um ambiente com Python e PyTorch.", "warn");
      return;
    }
    if (action === "status") {
      try {
        const plan = JSON.parse(api().read("training/sweep-request.json"));
        writeBlock(JSON.stringify(plan, null, 2), "info");
      } catch (error) {
        writeLine("Nenhum plano local foi encontrado. Use ai queue [quantidade].", "warn");
      }
      return;
    }
    throw new Error("Uso: ai info | ai queue [1..1000000] | ai status");
  }

  function execute(tokens) {
    if (!tokens.length) return;
    const [command, ...args] = tokens;
    if (command === "help") return showHelp();
    if (command === "clear") {
      output.replaceChildren();
      return;
    }
    if (command === "pwd") return writeLine("/project" + (cwd ? "/" + cwd : ""));
    if (command === "date") return writeLine(new Date().toString());
    if (tokens.includes(">")) {
      const redirectAt = tokens.indexOf(">");
      if (redirectAt === tokens.length - 1 || redirectAt > tokens.length - 2) throw new Error("Uso do redirecionamento: echo texto > arquivo");
      const target = resolvePath(tokens[redirectAt + 1]);
      const sourceTokens = tokens.slice(0, redirectAt);
      if (sourceTokens[0] !== "echo") throw new Error("Redirecionamento suportado apenas com echo: echo texto > arquivo");
      const text = sourceTokens.slice(1).join(" ") + "\n";
      const result = api().write(target, text);
      return writeLine("Redirecionado para " + target + " (" + result.bytes + " bytes)", "success");
    }
    if (command === "echo") return writeLine(args.join(" "));
    if (command === "history") {
      history.slice(-30).forEach((line, index) => writeLine(String(history.length - Math.min(30, history.length) + index + 1) + "  " + line, "muted"));
      return;
    }
    if (command === "ai") return handleAi(args);
    if (command === "check") return runCheck();
    if (command === "preview") {
      document.getElementById("preview-project").click();
      return writeLine("Pré-visualização solicitada. Só HTML presente em index.html será exibido.", "success");
    }
    if (command === "zip") {
      document.getElementById("export-zip").click();
      return writeLine("Exportação do ZIP solicitada; no Android, escolha o destino no seletor de arquivos.", "success");
    }
    if (command === "ls" || command === "dir") {
      const target = args[0] ? resolveDirectory(args[0]) : cwd;
      ensureDirectory(target);
      listDirectory(target);
      return;
    }
    if (command === "tree") {
      const target = args[0] ? resolveDirectory(args[0]) : cwd;
      ensureDirectory(target);
      writeLine(target ? target + "/" : ".");
      buildTree(target);
      return;
    }
    if (command === "cd") {
      requireArgs(args, 1, "cd <pasta|..|/>");
      const target = resolveDirectory(args[0]);
      ensureDirectory(target);
      cwd = target;
      setPrompt();
      return writeLine("Diretório atual: /project" + (cwd ? "/" + cwd : ""), "success");
    }
    if (command === "cat" || command === "head" || command === "tail" || command === "wc" || command === "stat") {
      requireArgs(args, 1, command + " <arquivo>");
      const path = resolvePath(args[0]);
      const content = api().read(path);
      const lines = content.split("\n");
      if (command === "cat") return writeBlock(content.length > 12000 ? content.slice(0, 12000) + "\n… saída truncada" : content);
      if (command === "head") return writeBlock(lines.slice(0, Math.min(200, Math.max(1, Number(args[1]) || 10))).join("\n"));
      if (command === "tail") return writeBlock(lines.slice(-Math.min(200, Math.max(1, Number(args[1]) || 10))).join("\n"));
      if (command === "wc") return writeLine(lines.length + " linhas  " + (content.trim() ? content.trim().split(/\s+/).length : 0) + " palavras  " + new TextEncoder().encode(content).byteLength + " bytes");
      if (command === "stat") return writeBlock("Arquivo: " + path + "\nBytes: " + new TextEncoder().encode(content).byteLength + "\nLinhas: " + lines.length + "\nÚltima modificação: informação não rastreada nesta versão");
    }
    if (command === "touch") {
      requireArgs(args, 1, "touch <arquivo>");
      const path = resolvePath(args[0]);
      const result = api().touch(path);
      return writeLine((result.created ? "Criado " : "Já existe ") + path, "success");
    }
    if (command === "mkdir") {
      requireArgs(args, 1, "mkdir <pasta>");
      const path = resolvePath(args[0]);
      const directory = api().mkdir(path);
      return writeLine("Pasta virtual criada: " + directory, "success");
    }
    if (command === "rmdir") {
      requireArgs(args, 1, "rmdir <pasta>");
      const path = resolvePath(args[0]);
      return writeLine("Pasta removida: " + api().rmdir(path), "success");
    }
    if (command === "write" || command === "append") {
      requireArgs(args, 2, command + " <arquivo> <texto>");
      const path = resolvePath(args[0]);
      const text = args.slice(1).join(" ") + "\n";
      const result = command === "append" ? api().append(path, text) : api().write(path, text);
      return writeLine((command === "append" ? "Acrescentado a " : result.created ? "Criado e escrito " : "Escrito em ") + path + " (" + result.bytes + " bytes)", "success");
    }
    if (command === "mv" || command === "rename") {
      requireArgs(args, 2, "mv <arquivo> <novo-caminho>");
      const from = resolvePath(args[0]);
      const to = resolvePath(args[1]);
      const result = api().rename(from, to);
      return writeLine("Movido: " + result.from + " -> " + result.to, "success");
    }
    if (command === "rm" || command === "del") {
      requireArgs(args, 1, "rm <arquivo>");
      const path = resolvePath(args[0]);
      if (!window.confirm("Excluir permanentemente do workspace local: " + path + "?")) {
        writeLine("Exclusão cancelada.", "warn");
        return;
      }
      return writeLine("Removido: " + api().remove(path), "success");
    }
    if (command === "grep") {
      requireArgs(args, 1, "grep <texto> [arquivo|pasta]");
      const query = args[0];
      const target = args[1] || ".";
      const files = matchingFiles(target);
      let matchCount = 0;
      for (const file of files) {
        const lines = file.content.split("\n");
        lines.forEach((line, index) => {
          if (line.toLocaleLowerCase("pt-BR").includes(query.toLocaleLowerCase("pt-BR"))) {
            writeLine(file.path + ":" + (index + 1) + ": " + line);
            matchCount += 1;
          }
        });
      }
      if (!matchCount) writeLine("Nenhuma ocorrência literal de " + JSON.stringify(query), "muted");
      return;
    }
    if (command === "find") {
      const target = args[0] || ".";
      const query = args[1] || "";
      const dir = resolveDirectory(target);
      ensureDirectory(dir);
      const prefix = dir ? dir + "/" : "";
      const nodes = new Set([
        ...api().getFiles().map(file => file.path),
        ...api().getDirectories()
      ]);
      const results = Array.from(nodes).filter(path => path.startsWith(prefix) && path.toLocaleLowerCase("pt-BR").includes(query.toLocaleLowerCase("pt-BR"))).sort();
      results.slice(0, 200).forEach(path => writeLine(path + (api().getDirectories().includes(path) ? "/" : "")));
      if (!results.length) writeLine("Nenhum caminho encontrado.", "muted");
      if (results.length > 200) writeLine("Exibidos 200 de " + results.length + " resultados.", "warn");
      return;
    }
    if (tokens.includes(">")) {
      const redirectAt = tokens.indexOf(">");
      if (redirectAt === tokens.length - 1 || redirectAt > tokens.length - 2) throw new Error("Uso do redirecionamento: echo texto > arquivo");
      const target = resolvePath(tokens[redirectAt + 1]);
      const sourceTokens = tokens.slice(0, redirectAt);
      if (sourceTokens[0] !== "echo") throw new Error("Redirecionamento suportado apenas com echo: echo texto > arquivo");
      const text = sourceTokens.slice(1).join(" ") + "\n";
      const result = api().write(target, text);
      return writeLine("Redirecionado para " + target + " (" + result.bytes + " bytes)", "success");
    }
    throw new Error("Comando desconhecido: " + command + ". Digite help.");
  }

  async function submitCommand(event) {
    event.preventDefault();
    const source = input.value.trim();
    if (!source) return;
    input.value = "";
    writeLine("~/" + (cwd ? cwd + "/" : "") + "$ " + source, "command");
    history.push(source);
    history = history.slice(-MAX_HISTORY);
    historyIndex = history.length;
    saveHistory();
    try {
      const tokens = tokenize(source);
      execute(tokens);
    } catch (error) {
      writeLine(error.message || "Falha no comando.", "error");
    }
    setPrompt();
    input.focus();
  }

  function togglePanel(open) {
    panel.hidden = !open;
    document.getElementById("toggle-terminal").setAttribute("aria-expanded", String(open));
    if (open) input.focus();
  }

  document.getElementById("toggle-terminal").addEventListener("click", () => togglePanel(panel.hidden));
  document.getElementById("close-terminal").addEventListener("click", () => togglePanel(false));
  document.getElementById("clear-terminal").addEventListener("click", () => output.replaceChildren());
  form.addEventListener("submit", submitCommand);
  input.addEventListener("keydown", event => {
    if (event.key === "ArrowUp") {
      event.preventDefault();
      if (!history.length) return;
      historyIndex = Math.max(0, historyIndex - 1);
      input.value = history[historyIndex] || "";
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      historyIndex = Math.min(history.length, historyIndex + 1);
      input.value = history[historyIndex] || "";
    } else if (event.key === "Escape") {
      togglePanel(false);
    }
  });
  document.addEventListener("keydown", event => {
    if ((event.ctrlKey || event.metaKey) && event.key === "`") {
      event.preventDefault();
      togglePanel(panel.hidden);
    }
  });

  setPrompt();
})();