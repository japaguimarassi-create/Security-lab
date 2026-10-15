(() => {
  "use strict";

  const engine = window.KodexWorkspaceEngine;
  const STORAGE_KEY = "kodex:project-workspace:v1";
  const ACTIONS_URL = "https://github.com/japaguimarassi-create/Security-lab/actions/workflows/kodex-ml-lab.yml";
  const state = { files: [], name: "Meu projeto", activePath: null };
  const elements = {
    output: document.getElementById("terminal-output"),
    form: document.getElementById("terminal-form"),
    input: document.getElementById("terminal-input"),
    path: document.getElementById("terminal-path"),
    runner: document.getElementById("terminal-runner"),
    toast: document.getElementById("terminal-toast"),
    actionLink: document.getElementById("open-workflow")
  };
  const history = [];
  let historyIndex = 0;
  let outputCount = 0;
  let activeRunId = null;
  let runTimeout = null;

  function loadProject() {
    try {
      const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
      const files = engine.collectEntries(stored?.files || engine.createStarterProject());
      state.files = files;
      state.name = typeof stored?.name === "string" ? stored.name : "Meu projeto";
      state.activePath = stored?.activePath || files[0]?.path || null;
    } catch (error) {
      state.files = engine.collectEntries(engine.createStarterProject());
      state.name = "Meu projeto";
      state.activePath = "index.html";
      writeLine("Aviso: não foi possível ler o workspace anterior; usando arquivos de exemplo.", "warning");
    }
  }

  function persistProject() {
    try {
      const entries = engine.collectEntries(state.files);
      if (entries.length > engine.MAX_FILES || engine.measureEntries(entries) > engine.MAX_PROJECT_BYTES) {
        throw new Error("Limite de tamanho do workspace excedido.");
      }
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        schemaVersion: 1,
        name: state.name,
        activePath: state.activePath,
        files: entries
      }));
      return true;
    } catch (error) {
      writeLine("Falha ao salvar o workspace: " + error.message, "error");
      return false;
    }
  }

  function filesByPath() {
    return Object.fromEntries(state.files.map(file => [file.path, file.content]));
  }

  function getFile(path) {
    try {
      const normalized = engine.normalizeProjectPath(path);
      return state.files.find(file => file.path === normalized) || null;
    } catch {
      return null;
    }
  }

  function putFile(path, content, overwrite = false) {
    const normalized = engine.normalizeProjectPath(path);
    const existing = getFile(normalized);
    if (existing && !overwrite) throw new Error("Arquivo já existe: " + normalized);
    if (typeof content !== "string") throw new Error("Conteúdo deve ser texto.");
    if (new TextEncoder().encode(content).byteLength > engine.MAX_FILE_BYTES) throw new Error("Arquivo excede 512 KiB.");
    if (existing) existing.content = content;
    else {
      if (state.files.length >= engine.MAX_FILES) throw new Error("Limite de 200 arquivos atingido.");
      state.files.push({ path: normalized, content });
    }
    state.activePath = normalized;
    if (!persistProject()) throw new Error("Não foi possível persistir o arquivo.");
    return normalized;
  }

  function tokenize(input) {
    const tokens = [];
    let current = "";
    let quote = "";
    let escaped = false;
    let active = false;
    for (const char of input) {
      if (escaped) {
        current += char;
        escaped = false;
        active = true;
        continue;
      }
      if (char === "\\" && quote !== "'") {
        escaped = true;
        active = true;
        continue;
      }
      if (quote) {
        if (char === quote) quote = "";
        else current += char;
        active = true;
        continue;
      }
      if (char === "'" || char === '"') {
        quote = char;
        active = true;
        continue;
      }
      if (/\s/.test(char)) {
        if (active) tokens.push(current);
        current = "";
        active = false;
        continue;
      }
      if ([";", "|", "&", ">", "<", "`"].includes(char)) {
        throw new Error("Operadores e substituições de shell não são executados. Use comandos separados.");
      }
      current += char;
      active = true;
    }
    if (escaped) current += "\\";
    if (quote) throw new Error("Aspas não foram fechadas.");
    if (active) tokens.push(current);
    return tokens;
  }

  function writeLine(text, kind = "normal") {
    const row = document.createElement("div");
    row.className = "terminal-line " + kind;
    row.textContent = String(text ?? "");
    elements.output.append(row);
    outputCount += 1;
    while (outputCount > 1000 && elements.output.firstChild) {
      elements.output.firstChild.remove();
      outputCount -= 1;
    }
    elements.output.scrollTop = elements.output.scrollHeight;
  }

  function writeBlock(text, kind = "normal") {
    String(text).split("\n").forEach(line => writeLine(line, kind));
  }

  function showToast(message) {
    elements.toast.textContent = message;
    elements.toast.hidden = false;
    window.setTimeout(() => { elements.toast.hidden = true; }, 2600);
  }

  function sortedFiles() {
    return [...state.files].sort((a, b) => a.path.localeCompare(b.path));
  }

  function treeText(files) {
    const root = {};
    for (const file of files) {
      let current = root;
      const parts = file.path.split("/");
      for (const part of parts.slice(0, -1)) {
        current[part] = current[part] && typeof current[part] === "object" ? current[part] : {};
        current = current[part];
      }
      current[parts[parts.length - 1]] = null;
    }
    const lines = [state.name + "/"];
    function visit(node, depth) {
      const entries = Object.keys(node).sort((a, b) => a.localeCompare(b));
      entries.forEach((name, index) => {
        const last = index === entries.length - 1;
        const value = node[name];
        lines.push("  ".repeat(depth) + (last ? "└─ " : "├─ ") + name + (value ? "/" : ""));
        if (value && typeof value === "object") visit(value, depth + 1);
      });
    }
    visit(root, 1);
    return lines.join("\n");
  }

  function formatBytes(bytes) {
    return bytes < 1024 ? bytes + " B" : (bytes / 1024).toFixed(1) + " KiB";
  }

  function runJavascript(file) {
    if (!file) {
      writeLine("Uso: run js <arquivo.js>", "warning");
      return;
    }
    if (!/\.(js|cjs|mjs)$/i.test(file.path)) {
      writeLine("O executor isolado aceita arquivos JavaScript (.js, .cjs, .mjs).", "error");
      return;
    }
    if (/^\s*(?:import\s|export\s)/m.test(file.content)) {
      writeLine("Imports/exports ES modules não são suportados pelo executor local. Use node --check ou prepare o build no GitHub.", "warning");
      return;
    }
    if (new TextEncoder().encode(file.content).byteLength > 128 * 1024) {
      writeLine("O executor local limita a fonte JavaScript a 128 KiB.", "error");
      return;
    }
    if (activeRunId) {
      writeLine("Já existe uma execução em andamento; aguarde ou interrompa a anterior.", "warning");
      return;
    }
    const runId = String(Date.now()) + "-" + Math.random().toString(36).slice(2);
    activeRunId = runId;
    const safeSource = file.content.replace(/<\/script/gi, "<\\/script");
    const csp = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-src 'none'";
    const bootstrap = "(function(){const runId=" + JSON.stringify(runId) + ";const send=function(level,values){let text;try{text=values.map(function(value){if(typeof value==='string')return value;if(value instanceof Error)return value.name+': '+value.message;try{return JSON.stringify(value)}catch{return String(value)}}).join(' ')}catch{text='[não foi possível formatar a saída]'}window.parent.postMessage({type:'kodex-terminal-log',runId:runId,level:level,text:text},'*')};console.log=function(){send('normal',Array.from(arguments))};console.info=function(){send('info',Array.from(arguments))};console.warn=function(){send('warning',Array.from(arguments))};console.error=function(){send('error',Array.from(arguments))};window.addEventListener('error',function(event){send('error',[event.message||'Erro de execução'])});window.addEventListener('unhandledrejection',function(event){send('error',[event.reason])});send('info',['Executor em iframe isolado; rede e acesso à origem foram restringidos.'])})();";
    const userScript = "try{(async function(){\n" + safeSource + "\n})().catch(function(error){console.error(error)})}catch(error){console.error(error)}";
    elements.runner.srcdoc = "<!doctype html><html><head><meta charset='utf-8'><meta http-equiv='Content-Security-Policy' content=\"" + csp + "\"></head><body><script>" + bootstrap + "</script><script>" + userScript + "</script></body></html>";
    writeLine("$ run js " + file.path, "command");
    writeLine("Executando JavaScript no navegador isolado. Não é Node.js e não fornece acesso ao sistema de arquivos.", "info");
    runTimeout = window.setTimeout(() => {
      if (activeRunId !== runId) return;
      writeLine("Tempo limite de 5 segundos atingido; a prévia foi encerrada.", "warning");
      stopJavascript();
    }, 5000);
  }

  function stopJavascript() {
    if (runTimeout) window.clearTimeout(runTimeout);
    runTimeout = null;
    activeRunId = null;
    elements.runner.srcdoc = "";
  }

  window.addEventListener("message", event => {
    if (event.source !== elements.runner.contentWindow || event.origin !== "null") return;
    const data = event.data;
    if (!data || data.type !== "kodex-terminal-log" || data.runId !== activeRunId) return;
    writeLine(data.text, data.level || "normal");
  });

  function commandHelp() {
    return [
      "KODEX PROJECT TERMINAL — comandos disponíveis",
      "",
      "help                           lista comandos",
      "pwd                            mostra /project",
      "ls [prefixo] | tree            lista arquivos",
      "cat <arquivo>                  mostra um arquivo",
      "head <arquivo> [linhas]        mostra o começo",
      "tail <arquivo> [linhas]        mostra o final",
      "grep <texto> [arquivo]         procura texto em arquivos",
      "find [texto]                   busca nomes de arquivo",
      "touch <arquivo>                cria arquivo vazio",
      "mkdir <pasta>                  cria pasta via .gitkeep",
      "write <arquivo> \"texto\"        cria/substitui texto",
      "append <arquivo> \"texto\"       acrescenta texto",
      "cp <origem> <destino>          copia arquivo",
      "mv <origem> <destino>          renomeia arquivo",
      "rm --yes <arquivo>             remove arquivo local",
      "node --check <arquivo.js>      checagem de sintaxe sem executar",
      "run js <arquivo.js>            executa JS em iframe isolado",
      "check                          checagens estáticas do projeto",
      "status                         estado e limites do workspace",
      "export                         baixa um ZIP do projeto",
      "edit <arquivo>                 abre o editor nesse arquivo",
      "open editor | open chat        abre a interface selecionada",
      "train plan [total] [shards] [por_shard] [lote]  planeja a fila",
      "train workflow                 abre o workflow de ML no GitHub",
      "clear                          limpa a tela do terminal",
      "",
      "Este não é um shell do Android/Linux. Não executa bash, apt, npm, pip ou comandos arbitrários.",
      "Treinos reais rodam no GitHub Actions; o planejador não afirma que os ensaios foram executados."
    ].join("\n");
  }

  function runChecks() {
    const report = engine.validateProject(filesByPath());
    writeLine(
      "Checagem estática: " + report.passed + " aprovado(s), " + report.warnings + " aviso(s), " + report.failed + " falha(s).",
      report.failed ? "error" : "success"
    );
    for (const check of report.checks) {
      const mark = check.status === "pass" ? "PASS" : check.status === "warn" ? "WARN" : "FAIL";
      writeLine("[" + mark + "] " + check.title + ": " + check.detail, check.status === "fail" ? "error" : check.status === "warn" ? "warning" : "normal");
    }
    writeLine("Isso não compila dependências ou binários e não substitui testes reais.", "info");
  }

  function planTraining(totalRaw, shardsRaw, perShardRaw, batchRaw) {
    const total = totalRaw === undefined ? 1000000 : Number(totalRaw);
    const shards = shardsRaw === undefined ? 16 : Number(shardsRaw);
    const perShard = perShardRaw === undefined ? 1 : Number(perShardRaw);
    const batchIndex = batchRaw === undefined ? 0 : Number(batchRaw);
    if (!Number.isSafeInteger(total) || total < 1 || total > 1000000000) {
      writeLine("total deve estar entre 1 e 1.000.000.000.", "error");
      return;
    }
    if (!Number.isSafeInteger(shards) || shards < 1 || shards > 256) {
      writeLine("shards deve estar entre 1 e 256: o GitHub Actions limita cada matriz a 256 trabalhos.", "error");
      return;
    }
    if (!Number.isSafeInteger(perShard) || perShard < 1 || perShard > 100) {
      writeLine("por_shard deve estar entre 1 e 100 experimentos sequenciais por trabalho.", "error");
      return;
    }
    if (!Number.isSafeInteger(batchIndex) || batchIndex < 0 || batchIndex > 10000000) {
      writeLine("lote deve estar entre 0 e 10.000.000.", "error");
      return;
    }
    const candidatesPerBatch = shards * perShard;
    const batchCount = Math.ceil(total / candidatesPerBatch);
    const pendingBeforeBatch = Math.min(total, batchIndex * candidatesPerBatch);
    const remainingBeforeBatch = Math.max(0, total - pendingBeforeBatch);
    const candidatesInThisBatch = Math.min(candidatesPerBatch, remainingBeforeBatch);
    writeLine("Plano da fila experimental", "heading");
    writeLine("Candidatos totais: " + total.toLocaleString("pt-BR"));
    writeLine("Trabalhos por matriz: até " + shards + " (limite técnico de 256)");
    writeLine("Experimentos sequenciais por trabalho: " + perShard);
    writeLine("Candidatos por lote: até " + candidatesPerBatch.toLocaleString("pt-BR"));
    writeLine("Lote atual: " + batchIndex + " de " + (batchCount - 1));
    writeLine("Candidatos deste lote: " + candidatesInThisBatch.toLocaleString("pt-BR"));
    writeLine("Lotes estimados para cobrir todos os candidatos: " + batchCount.toLocaleString("pt-BR"));
    writeLine("Arquitetura do treino: Transformer causal com RoPE, GQA, MoE e multi-token prediction; a configuração é verificada no workflow.", "success");
    writeLine("Estado: PLANEJADO. Nenhum desses treinos foi executado por este comando.", "warning");
    writeLine("A execução simultânea real pode ser menor por quotas e disponibilidade dos runners do GitHub.", "info");
    writeLine("Um milhão de candidatos não equivale automaticamente a anos de aprendizagem. Registre tokens, passos, tempo, hardware e métricas.", "info");
    writeLine("Inicie ou confira a execução real em Actions: " + ACTIONS_URL, "link");
  }

  function downloadProject() {
    try {
      const bytes = engine.buildProjectZip(state.files);
      const blob = new Blob([bytes], { type: "application/zip" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = (state.name || "kodex-projeto").replace(/[^a-z0-9_-]+/gi, "-") + ".zip";
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      writeLine("ZIP criado com " + state.files.length + " arquivo(s).", "success");
    } catch (error) {
      writeLine("Erro ao exportar: " + error.message, "error");
    }
  }

  function executeCommand(rawInput) {
    const input = rawInput.trim();
    if (!input) return;
    writeLine("$ " + input, "command");
    if (history[history.length - 1] !== input) history.push(input);
    historyIndex = history.length;
    let args;
    try {
      args = tokenize(input);
    } catch (error) {
      writeLine(error.message, "error");
      return;
    }
    const command = args.shift()?.toLowerCase();
    if (!command) return;
    try {
      if (command === "help" || command === "?") {
        writeBlock(commandHelp(), "info");
      } else if (command === "clear" || command === "cls") {
        elements.output.replaceChildren();
        outputCount = 0;
      } else if (command === "pwd") {
        writeLine("/project");
      } else if (command === "whoami") {
        writeLine("kodex-local-user · projeto local sem privilégios de sistema", "info");
      } else if (command === "ls" || command === "dir") {
        const prefix = args[0] || "";
        const matches = sortedFiles().filter(file => file.path.startsWith(prefix));
        writeBlock(matches.length ? matches.map(file => file.path + "  " + formatBytes(new TextEncoder().encode(file.content).length)).join("\n") : "(nenhum arquivo)", "normal");
      } else if (command === "tree") {
        writeBlock(treeText(sortedFiles()));
      } else if (command === "cat" || command === "type") {
        if (!args[0]) throw new Error("Uso: cat <arquivo>");
        const file = getFile(args[0]);
        if (!file) throw new Error("Arquivo não encontrado: " + args[0]);
        writeBlock(file.content || "(arquivo vazio)", "normal");
      } else if (command === "head" || command === "tail") {
        if (!args.length) throw new Error("Uso: " + command + " <arquivo> [linhas]");
        let path = args[0];
        let count = Number(args[1] || 10);
        if (/^\d+$/.test(args[0]) && args[1]) {
          count = Number(args[0]);
          path = args[1];
        }
        const file = getFile(path);
        if (!file) throw new Error("Arquivo não encontrado: " + path);
        if (!Number.isInteger(count) || count < 1 || count > 500) throw new Error("Linhas precisa estar entre 1 e 500.");
        const lines = file.content.split("\n");
        writeBlock((command === "head" ? lines.slice(0, count) : lines.slice(-count)).join("\n"));
      } else if (command === "grep") {
        if (!args[0]) throw new Error('Uso: grep "texto" [arquivo]');
        const needle = args[0].toLocaleLowerCase("pt-BR");
        const files = args[1] ? [getFile(args[1])].filter(Boolean) : sortedFiles();
        if (args[1] && !files.length) throw new Error("Arquivo não encontrado: " + args[1]);
        let hits = 0;
        for (const file of files) {
          file.content.split("\n").forEach((line, index) => {
            if (line.toLocaleLowerCase("pt-BR").includes(needle)) {
              writeLine(file.path + ":" + (index + 1) + ": " + line);
              hits += 1;
            }
          });
        }
        if (!hits) writeLine("Nenhuma ocorrência encontrada.", "info");
      } else if (command === "find") {
        const needle = (args[0] || "").toLocaleLowerCase("pt-BR");
        const files = sortedFiles().filter(file => file.path.toLocaleLowerCase("pt-BR").includes(needle));
        writeBlock(files.length ? files.map(file => file.path).join("\n") : "(nenhum arquivo)");
      } else if (command === "touch") {
        if (!args[0]) throw new Error("Uso: touch <arquivo>");
        const path = putFile(args[0], "");
        writeLine("Criado: " + path, "success");
      } else if (command === "mkdir") {
        if (!args[0]) throw new Error("Uso: mkdir <pasta>");
        const directory = engine.normalizeProjectPath(args[0].replace(/\/$/, ""));
        const path = putFile(directory + "/.gitkeep", "");
        writeLine("Pasta representada por " + path, "success");
      } else if (command === "write" || command === "append") {
        if (args.length < 2) throw new Error('Uso: ' + command + ' <arquivo> "texto"');
        const path = engine.normalizeProjectPath(args.shift());
        const content = args.join(" ");
        const current = getFile(path);
        if (command === "append" && !current) throw new Error("Arquivo não encontrado. Use write para criar.");
        const result = putFile(path, command === "append" ? current.content + content : content, true);
        writeLine("Salvo localmente: " + result, "success");
      } else if (command === "cp" || command === "mv") {
        if (args.length !== 2) throw new Error("Uso: " + command + " <origem> <destino>");
        const source = getFile(args[0]);
        if (!source) throw new Error("Origem não encontrada: " + args[0]);
        const targetPath = engine.normalizeProjectPath(args[1]);
        if (getFile(targetPath)) throw new Error("Destino já existe: " + targetPath);
        const result = putFile(targetPath, source.content, false);
        if (command === "mv") {
          state.files = state.files.filter(file => file.path !== source.path);
          persistProject();
        }
        writeLine(command === "cp" ? "Copiado para: " + result : "Movido para: " + result, "success");
      } else if (command === "rm" || command === "del") {
        if (args[0] !== "--yes" || !args[1]) throw new Error("Exclusão local protegida. Use rm --yes <arquivo>.");
        const file = getFile(args[1]);
        if (!file) throw new Error("Arquivo não encontrado: " + args[1]);
        state.files = state.files.filter(entry => entry.path !== file.path);
        state.activePath = state.files[0]?.path || null;
        persistProject();
        writeLine("Removido do projeto local: " + file.path, "success");
      } else if (command === "node") {
        if (args[0] !== "--check" || !args[1]) throw new Error("Node.js do sistema não está disponível. Use node --check <arquivo.js> para checagem estática.");
        const file = getFile(args[1]);
        if (!file) throw new Error("Arquivo não encontrado: " + args[1]);
        if (/^\s*(?:import\s|export\s)/m.test(file.content)) {
          writeLine("Não verificado: módulo ES. A checagem local não carrega módulos ou dependências.", "warning");
        } else {
          new Function(file.content);
          writeLine("Sintaxe JavaScript válida: " + file.path + ". O código não foi executado.", "success");
        }
      } else if (command === "run") {
        if (args[0] !== "js") throw new Error("Apenas 'run js <arquivo.js>' está disponível no terminal local.");
        if (!args[1]) throw new Error("Uso: run js <arquivo.js>");
        const file = getFile(args[1]);
        if (!file) throw new Error("Arquivo não encontrado: " + args[1]);
        runJavascript(file);
      } else if (command === "check") {
        runChecks();
      } else if (command === "status") {
        const report = engine.validateProject(filesByPath());
        writeLine("Projeto: " + state.name);
        writeLine("Arquivos: " + state.files.length + "/" + engine.MAX_FILES);
        writeLine("Tamanho: " + formatBytes(engine.measureEntries(state.files)) + " / " + formatBytes(engine.MAX_PROJECT_BYTES));
        writeLine("Checagem estática: " + report.failed + " falha(s), " + report.warnings + " aviso(s).");
        writeLine("Execução do SO, GitHub conectado e treino neural: não disponíveis neste terminal local.", "info");
      } else if (command === "export") {
        downloadProject();
      } else if (command === "edit") {
        if (!args[0]) throw new Error("Uso: edit <arquivo>");
        const file = getFile(args[0]);
        if (!file) throw new Error("Arquivo não encontrado: " + args[0]);
        state.activePath = file.path;
        persistProject();
        window.location.href = "./workspace.html";
      } else if (command === "open") {
        const destination = (args[0] || "").toLowerCase();
        if (destination === "editor") window.location.href = "./workspace.html";
        else if (destination === "chat") window.location.href = "./index.html";
        else if (destination === "workflow" || destination === "train") window.open(ACTIONS_URL, "_blank", "noopener,noreferrer");
        else throw new Error("Uso: open editor | open chat | open workflow");
      } else if (command === "train") {
        const action = (args[0] || "plan").toLowerCase();
        if (action === "plan") planTraining(args[1], args[2], args[3], args[4]);
        else if (action === "workflow" || action === "github") {
          writeLine("Abrindo GitHub Actions. A execução real será registrada pelo workflow; este terminal não dispara jobs por conta própria.", "info");
          window.open(ACTIONS_URL, "_blank", "noopener,noreferrer");
        } else if (action === "status") {
          writeLine("Estado de treinos remotos não pode ser lido sem conectar à API do GitHub. Abra Actions para ver os logs reais.", "warning");
          window.open(ACTIONS_URL, "_blank", "noopener,noreferrer");
        } else {
          throw new Error("Uso: train plan [total_trials] [shards] | train workflow | train status");
        }
      } else if (command === "python" || command === "bash" || command === "sh" || command === "npm" || command === "pip" || command === "apt" || command === "git") {
        writeLine("Este terminal web não executa " + command + " no sistema operacional. Use o workflow do GitHub para treinos/builds reais, ou Termux para comandos locais.", "warning");
      } else if (command === "echo") {
        writeLine(args.join(" "));
      } else if (command === "date") {
        writeLine(new Date().toISOString());
      } else if (command === "history") {
        writeBlock(history.map((item, index) => (index + 1) + "  " + item).join("\n"));
      } else if (command === "exit") {
        writeLine("O terminal local continua aberto; use a navegação para voltar ao chat.");
      } else {
        writeLine("Comando desconhecido: " + command + ". Digite help.", "error");
      }
    } catch (error) {
      writeLine(error.message || "Falha ao executar comando.", "error");
    }
  }

  elements.form.addEventListener("submit", event => {
    event.preventDefault();
    const value = elements.input.value;
    elements.input.value = "";
    executeCommand(value);
    elements.input.focus();
  });

  elements.input.addEventListener("keydown", event => {
    if (event.key === "ArrowUp") {
      if (!history.length) return;
      event.preventDefault();
      historyIndex = Math.max(0, historyIndex - 1);
      elements.input.value = history[historyIndex] || "";
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      historyIndex = Math.min(history.length, historyIndex + 1);
      elements.input.value = history[historyIndex] || "";
    } else if (event.key === "Tab") {
      event.preventDefault();
      const current = elements.input.value.trim();
      const choices = ["help", "pwd", "ls", "tree", "cat", "grep", "find", "touch", "mkdir", "write", "append", "cp", "mv", "rm", "check", "status", "export", "edit", "run js", "train plan"];
      const matches = choices.filter(item => item.startsWith(current));
      if (matches.length === 1) elements.input.value = matches[0] + " ";
    } else if (event.ctrlKey && event.key.toLowerCase() === "c") {
      if (activeRunId) {
        stopJavascript();
        writeLine("^C · execução do iframe interrompida.", "warning");
      }
    }
  });

  document.getElementById("clear-terminal").addEventListener("click", () => {
    elements.output.replaceChildren();
    outputCount = 0;
    elements.input.focus();
  });
  document.getElementById("interrupt-run").addEventListener("click", () => {
    if (!activeRunId) {
      writeLine("Nenhuma execução em andamento.", "info");
      return;
    }
    stopJavascript();
    writeLine("Execução interrompida.", "warning");
  });
  elements.actionLink.addEventListener("click", () => {
    writeLine("O workflow do GitHub é a superfície de compilação/treino remoto; esta página não tem credenciais para iniciar execuções por API.", "info");
  });

  loadProject();
  elements.path.textContent = "/project · " + state.name;
  writeLine("Kodex Project Terminal 0.5.0", "heading");
  writeLine("Workspace local • arquivos persistidos no navegador/WebView • execução JavaScript isolada.", "info");
  writeLine("GitHub Actions é o executor remoto de treinamento/build. Nenhum APK será compilado por este terminal.", "info");
  writeLine("Digite help para ver comandos, ls para listar arquivos ou train plan para planejar ensaios.", "info");
  elements.input.focus();
})();