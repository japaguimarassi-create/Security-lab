(() => {
  "use strict";
  const engine = window.KodexWorkspaceEngine;
  const STORAGE_KEY = "kodex:project-workspace:v1";
  const PLAN_KEY = "kodex:training-queue-plan:v1";
  const MAX_TRIALS = 10000000;
  const MAX_WORKERS = 32;
  const el = {
    output: document.getElementById("terminal-output"),
    form: document.getElementById("terminal-form"),
    input: document.getElementById("terminal-input"),
    directory: document.getElementById("current-directory"),
    status: document.getElementById("project-status"),
    importInput: document.getElementById("import-input"),
    preview: document.getElementById("preview-shell"),
    previewFrame: document.getElementById("preview-frame"),
    toast: document.getElementById("toast")
  };
  let cwd = "";
  let history = [];
  let historyIndex = 0;
  let toastTimer = null;
  let project = loadProject();

  function loadProject() {
    try {
      const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
      if (parsed && Array.isArray(parsed.files)) {
        return { name: String(parsed.name || "Meu projeto"), files: engine.collectEntries(parsed.files) };
      }
    } catch {
      try { localStorage.removeItem(STORAGE_KEY); } catch {}
    }
    return { name: "Meu projeto", files: engine.collectEntries(engine.createStarterProject()) };
  }

  function saveProject() {
    const files = engine.collectEntries(project.files);
    if (files.length > engine.MAX_FILES) throw new Error("Limite de 200 arquivos atingido.");
    for (const file of files) {
      if (new TextEncoder().encode(file.content).length > engine.MAX_FILE_BYTES) {
        throw new Error("O arquivo " + file.path + " ultrapassa 512 KiB.");
      }
    }
    if (engine.measureEntries(files) > engine.MAX_PROJECT_BYTES) throw new Error("Limite de 1.500 KiB do projeto atingido.");
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      schemaVersion: 1,
      name: project.name,
      activePath: files[0]?.path || null,
      files
    }));
    project.files = files;
    updateStatus();
  }

  function updateStatus() {
    el.status.textContent = project.name + " · " + project.files.length + " arquivo(s)";
    el.directory.textContent = "/project" + (cwd ? "/" + cwd : "");
  }

  function toast(message) {
    el.toast.textContent = message;
    el.toast.hidden = false;
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { el.toast.hidden = true; }, 2800);
  }

  function output(text, kind = "result") {
    const item = document.createElement("div");
    item.className = "output-entry " + kind;
    item.textContent = String(text ?? "");
    el.output.append(item);
    while (el.output.children.length > 350) el.output.firstElementChild.remove();
    el.output.scrollTop = el.output.scrollHeight;
  }

  function tokenize(line) {
    const tokens = [];
    let current = "";
    let quote = "";
    let active = false;
    let escaped = false;
    const flush = () => {
      if (active) tokens.push(current);
      current = "";
      active = false;
    };
    for (let i = 0; i < line.length; i++) {
      const ch = line[i];
      if (escaped) {
        current += ch;
        escaped = false;
        active = true;
      } else if (quote && ch === "\\") {
        escaped = true;
      } else if (quote) {
        if (ch === quote) quote = "";
        else current += ch;
        active = true;
      } else if (ch === "'" || ch === '"') {
        quote = ch;
        active = true;
      } else if (/\s/.test(ch)) {
        flush();
      } else if (";|><&".includes(ch)) {
        flush();
        const next = line[i + 1] === ch && (ch === "&" || ch === "|" ) ? ch + line[++i] : ch;
        tokens.push(next);
      } else {
        current += ch;
        active = true;
      }
    }
    if (quote) throw new Error("Aspas não fechadas.");
    if (escaped) current += "\\";
    flush();
    return tokens;
  }

  function resolvePath(value, base = cwd, allowParent = false) {
    if (typeof value !== "string" || !value.trim()) throw new Error("Informe um caminho relativo.");
    const raw = value.trim().replace(/\\/g, "/");
    if (raw.startsWith("/") || raw.startsWith("//") || /^[a-z]:/i.test(raw)) {
      throw new Error("Caminhos absolutos não são permitidos.");
    }
    const parts = base ? base.split("/") : [];
    const segments = raw.split("/");
    if (segments.some(segment => !segment || segment.length > 120)) throw new Error("Segmento de caminho inválido.");
    for (const segment of segments) {
      if (segment === ".") continue;
      if (segment === "..") {
        if (!allowParent || !parts.length) throw new Error("Caminhos que escapam do projeto não são permitidos.");
        parts.pop();
      } else {
        parts.push(segment);
      }
    }
    return parts.length ? engine.normalizeProjectPath(parts.join("/")) : "";
  }

  function resolveFilePath(value) {
    return resolvePath(value, cwd, false);
  }

  function filesByPath() {
    return Object.fromEntries(project.files.map(file => [file.path, file.content]));
  }

  function findFile(path) {
    return project.files.find(file => file.path === path) || null;
  }

  function isDirectory(path) {
    const prefix = path ? path + "/" : "";
    return project.files.some(file => file.path.startsWith(prefix) && file.path !== path);
  }

  function listDirectory(path = cwd) {
    if (path && !isDirectory(path)) throw new Error("Pasta não encontrada: " + path);
    const prefix = path ? path + "/" : "";
    const results = new Map();
    for (const file of project.files) {
      if (!file.path.startsWith(prefix)) continue;
      const rest = file.path.slice(prefix.length);
      const parts = rest.split("/");
      if (parts[0] === ".gitkeep" || parts[0] === ".kodex-folder") continue;
      results.set(parts[0], parts.length > 1 ? "dir" : "file");
    }
    const sorted = [...results].sort((a, b) => a[1] === b[1] ? a[0].localeCompare(b[0]) : a[1] === "dir" ? -1 : 1);
    return sorted.length ? sorted.map(([name, type]) => (type === "dir" ? "[DIR] " : "      ") + name).join("\n") : "(pasta vazia)";
  }

  function addFile(path, content = "") {
    engine.normalizeProjectPath(path);
    if (findFile(path)) throw new Error("O arquivo já existe: " + path);
    if (project.files.length >= engine.MAX_FILES) throw new Error("Limite de arquivos atingido.");
    project.files.push({ path, content });
    saveProject();
  }

  function validate() {
    const report = engine.validateProject(filesByPath());
    return [
      "Checagens estáticas: " + report.passed + " OK, " + report.warnings + " avisos, " + report.failed + " falhas.",
      ...report.checks.map(check => "[" + check.status.toUpperCase() + "] " + check.title + ": " + check.detail),
      "Essas checagens não executam o programa nem substituem testes ou compilação reais."
    ].join("\n");
  }

  function trainingCommand(args) {
    const operation = (args[0] || "help").toLowerCase();
    if (operation === "architecture") {
      return [
        "Transformer causal decoder-only; embeddings de entrada/saída compartilhados.",
        "Configuração padrão com vocabulário 1024: 2.002.048 parâmetros treináveis.",
        "A contagem real depende do vocabulário BPE produzido pelo corpus.",
        "Parâmetros não são neurônios biológicos; esse tamanho não equivale ao Codex/Copilot.",
        "Nenhum treino foi executado por este comando do navegador."
      ].join("\n");
    }
    if (operation === "plan") {
      const trials = Number.parseInt(args[1] || "1000000", 10);
      const workers = Number.parseInt(args[2] || "2", 10);
      if (!Number.isSafeInteger(trials) || trials < 1 || trials > MAX_TRIALS) {
        throw new Error("Experimentos devem ficar entre 1 e " + MAX_TRIALS.toLocaleString("pt-BR") + ".");
      }
      if (!Number.isSafeInteger(workers) || workers < 1 || workers > MAX_WORKERS) {
        throw new Error("Workers devem ficar entre 1 e " + MAX_WORKERS + ".");
      }
      const plan = {
        schemaVersion: 1,
        trials,
        workers,
        createdAt: new Date().toISOString(),
        status: "planned-only-in-browser",
        targetParameters: 2002048
      };
      localStorage.setItem(PLAN_KEY, JSON.stringify(plan));
      return [
        "Plano registrado localmente. Nenhum treino foi executado no navegador.",
        "Experimentos planejados: " + trials.toLocaleString("pt-BR"),
        "Workers pretendidos: " + workers,
        "",
        "Fila SQLite e execução real no ambiente Python:",
        "python -m kodex_ai.sweep plan --trials " + trials + " --steps 1000",
        "python -m kodex_ai.sweep run --workers " + workers + " --max-completions " + workers + " --device auto",
        "",
        "Milhões de tarefas podem ficar na fila; o número ativo precisa respeitar CPU, memória e hardware disponíveis."
      ].join("\n");
    }
    if (operation === "status") {
      try {
        const plan = JSON.parse(localStorage.getItem(PLAN_KEY) || "null");
        if (!plan) return "Nenhum plano local. Execute: train plan 1000000 2";
        return [
          "Estado: " + plan.status,
          "Experimentos planejados: " + Number(plan.trials).toLocaleString("pt-BR"),
          "Workers desejados: " + plan.workers,
          "Criado: " + plan.createdAt,
          "Isso não é o estado da fila SQLite e não indica treinos executados."
        ].join("\n");
      } catch {
        return "Plano local ilegível; crie outro com train plan 1000000 2.";
      }
    }
    if (operation === "run") {
      const steps = Number.parseInt(args[1] || "1000", 10);
      if (!Number.isSafeInteger(steps) || steps < 1 || steps > 10000000) throw new Error("steps precisa ficar entre 1 e 10.000.000.");
      return [
        "Esta página não executa PyTorch nem processos do sistema.",
        "Comando real: python -m kodex_ai.train --steps " + steps + " --data training/data/mobile_dialogue.jsonl --output-dir artifacts/kodex-ai-run",
        "Após treinar: python -m kodex_ai.chat --checkpoint artifacts/kodex-ai-run/checkpoint_best.pt"
      ].join("\n");
    }
    return "Uso: train architecture | train plan [experimentos] [workers] | train status | train run [passos]";
  }

  function help() {
    return [
      "Comandos de projeto:",
      "  help                     mostra esta ajuda",
      "  pwd / cd [pasta]          mostra/navega dentro do projeto",
      "  ls [pasta] / tree          lista arquivos",
      "  cat arquivo               mostra texto",
      "  touch arquivo             cria arquivo vazio",
      "  mkdir pasta               cria marcador de pasta",
      "  write arquivo \"texto\"      cria um arquivo novo",
      "  append arquivo \"texto\"     acrescenta conteúdo",
      "  mv origem destino          move/renomeia sem sobrescrever",
      "  rm arquivo                 pede confirmação",
      "  grep \"padrão\" [arquivo]    busca por expressão regular",
      "  wc arquivo                 conta linhas/palavras/bytes",
      "  check                      valida JSON, JS clássico e HTML básicos",
      "  preview / import / export  prévia isolada, importar, exportar ZIP",
      "  train architecture        perfil do Transformer",
      "  train plan 1000000 2      plano de fila, sem executar treino no browser",
      "  train status / run 1000    status do plano ou comando de treino real",
      "  clear / exit               limpa saída ou fecha a sessão da página",
      "",
      "Para um terminal real no sistema local: python -m kodex_ai.terminal",
      "Para treinamento real: instale PyTorch e use python -m kodex_ai.train."
    ].join("\n");
  }

  function exportProject() {
    const bytes = engine.buildProjectZip(filesByPath());
    const url = URL.createObjectURL(new Blob([bytes], { type: "application/zip" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = (project.name || "kodex-projeto").replace(/[^a-z0-9-_]+/gi, "-") + ".zip";
    anchor.rel = "noopener";
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function previewProject() {
    try {
      el.previewFrame.srcdoc = engine.buildPreviewHtml(filesByPath());
      el.preview.hidden = false;
    } catch (error) {
      output(error.message, "error");
    }
  }

  async function importFiles() {
    const chosen = Array.from(el.importInput.files || []);
    el.importInput.value = "";
    if (!chosen.length) return;
    try {
      const additions = [];
      for (const file of chosen) {
        if (file.size > engine.MAX_FILE_BYTES) throw new Error(file.name + " ultrapassa 512 KiB.");
        const path = engine.normalizeProjectPath(file.webkitRelativePath || file.name);
        const content = await file.text();
        if (content.includes("\u0000")) throw new Error(file.name + " parece ser binário.");
        additions.push({ path, content });
      }
      const map = new Map(project.files.map(file => [file.path, file.content]));
      const clashes = additions.filter(file => map.has(file.path));
      if (clashes.length && !window.confirm("Substituir arquivos existentes? " + clashes.map(file => file.path).join(", "))) return;
      for (const file of additions) map.set(file.path, file.content);
      const candidate = engine.collectEntries(Array.from(map, ([path, content]) => ({ path, content })));
      if (candidate.length > engine.MAX_FILES || engine.measureEntries(candidate) > engine.MAX_PROJECT_BYTES) throw new Error("A importação excede os limites do projeto.");
      project.files = candidate;
      saveProject();
      output(additions.length + " arquivo(s) importado(s).", "success");
    } catch (error) {
      output("Falha na importação: " + error.message, "error");
    }
  }

  function execute(line) {
    let args;
    try {
      args = tokenize(line);
    } catch (error) {
      output(error.message, "error");
      return;
    }
    if (!args.length) return;
    if (args.some(arg => [";", "|", ">", "<", "&&", "||"].includes(arg))) {
      output("Operadores de shell não são executados nesta página. Use o CLI Python para comandos do sistema.", "error");
      return;
    }
    const command = args[0].toLowerCase();
    const values = args.slice(1);
    try {
      if (command === "help" || command === "man") return output(help());
      if (command === "clear" || command === "cls") return el.output.replaceChildren();
      if (command === "exit" || command === "quit") return output("Volte ao chat ou feche esta aba; nenhum processo de sistema está ativo.");
      if (command === "pwd") return output("/project" + (cwd ? "/" + cwd : ""));
      if (command === "cd") {
        const next = resolvePath(values[0] || ".", cwd, true);
        if (next && !isDirectory(next)) throw new Error("Pasta não encontrada: " + next);
        cwd = next;
        updateStatus();
        return output("/project" + (cwd ? "/" + cwd : ""), "success");
      }
      if (command === "ls" || command === "dir") return output(listDirectory(values[0] ? resolvePath(values[0], cwd, true) : cwd));
      if (command === "tree") return output("." + (cwd ? "/" + cwd : "") + "/\n" + project.files.map(file => "  " + file.path).join("\n"));
      if (command === "cat") {
        if (values.length !== 1) throw new Error("Uso: cat arquivo");
        const file = findFile(resolveFilePath(values[0]));
        if (!file) throw new Error("Arquivo não encontrado.");
        if (new TextEncoder().encode(file.content).length > 150000) throw new Error("Arquivo acima de 150 KiB; abra no editor.");
        return output(file.content || "(arquivo vazio)");
      }
      if (["touch", "write", "append", "mkdir"].includes(command)) {
        if (!values.length) throw new Error("Informe o caminho.");
        const path = resolveFilePath(values[0]);
        if (command === "mkdir") {
          if (isDirectory(path)) return output("A pasta já existe: " + path);
          addFile(path + "/.gitkeep", "");
          return output("Marcador de pasta criado: " + path, "success");
        }
        const body = values.slice(1).join(" ");
        if (command === "touch") {
          addFile(path, "");
          return output("Arquivo criado: " + path, "success");
        }
        if (command === "write") {
          addFile(path, body);
          return output("Arquivo criado: " + path, "success");
        }
        const file = findFile(path);
        if (!file) addFile(path, body);
        else {
          const next = file.content + (file.content ? "\n" : "") + body;
          if (new TextEncoder().encode(next).length > engine.MAX_FILE_BYTES) throw new Error("Arquivo ultrapassaria 512 KiB.");
          file.content = next;
          saveProject();
        }
        return output("Conteúdo acrescentado: " + path, "success");
      }
      if (command === "mv") {
        if (values.length !== 2) throw new Error("Uso: mv origem destino");
        const source = resolveFilePath(values[0]);
        const destination = resolveFilePath(values[1]);
        const file = findFile(source);
        if (!file) throw new Error("Arquivo de origem não encontrado.");
        if (findFile(destination)) throw new Error("O destino já existe.");
        file.path = engine.normalizeProjectPath(destination);
        saveProject();
        return output(source + " → " + destination, "success");
      }
      if (command === "rm") {
        if (values.length !== 1) throw new Error("Uso: rm arquivo");
        const path = resolveFilePath(values[0]);
        if (!findFile(path)) throw new Error("Arquivo não encontrado.");
        if (!window.confirm("Excluir " + path + " do workspace local?")) return output("Exclusão cancelada.");
        project.files = project.files.filter(file => file.path !== path);
        saveProject();
        return output("Arquivo removido: " + path, "success");
      }
      if (command === "grep") {
        if (!values.length) throw new Error('Uso: grep "padrão" [arquivo]');
        const pattern = new RegExp(values[0], "i");
        const target = values[1] ? resolveFilePath(values[1]) : null;
        const matches = [];
        for (const file of project.files) {
          if (target && file.path !== target) continue;
          if (file.content.length > 150000) continue;
          file.content.split("\n").forEach((text, index) => {
            if (pattern.test(text)) matches.push(file.path + ":" + (index + 1) + ": " + text);
          });
          if (matches.length >= 200) break;
        }
        return output(matches.length ? matches.slice(0, 200).join("\n") : "Nenhuma ocorrência encontrada.");
      }
      if (command === "wc") {
        if (values.length !== 1) throw new Error("Uso: wc arquivo");
        const file = findFile(resolveFilePath(values[0]));
        if (!file) throw new Error("Arquivo não encontrado.");
        return output(file.content.split("\n").length + " linhas · " + file.content.trim().split(/\s+/).filter(Boolean).length + " palavras · " + new TextEncoder().encode(file.content).length + " bytes");
      }
      if (command === "check" || command === "verify") return output(validate());
      if (command === "preview") return previewProject();
      if (command === "import") { el.importInput.click(); return output("Selecione arquivos de texto para importar."); }
      if (command === "export") { exportProject(); return output("ZIP de " + project.files.length + " arquivo(s) solicitado.", "success"); }
      if (command === "open" && ["workspace", "files"].includes(values[0])) { window.location.href = "./workspace.html"; return; }
      if (command === "train") return output(trainingCommand(values));
      if (["run", "python", "python3", "node", "npm", "git"].includes(command)) {
        return output("Esta página não executa processos do sistema. Use python -m kodex_ai.terminal no ambiente local ou o workflow Python do GitHub Actions.", "error");
      }
      return output("Comando desconhecido: " + command + ". Digite help.", "error");
    } catch (error) {
      output("Erro: " + error.message, "error");
    }
  }

  el.form.addEventListener("submit", event => {
    event.preventDefault();
    const line = el.input.value.trim();
    if (!line) return;
    history.push(line);
    historyIndex = history.length;
    output("kodex:" + (cwd ? "/" + cwd : "/project") + " › " + line, "command");
    el.input.value = "";
    execute(line);
    el.input.focus();
  });
  el.input.addEventListener("keydown", event => {
    if (event.key === "ArrowUp" && history.length) {
      event.preventDefault();
      historyIndex = Math.max(0, historyIndex - 1);
      el.input.value = history[historyIndex] || "";
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      historyIndex = Math.min(history.length, historyIndex + 1);
      el.input.value = history[historyIndex] || "";
    }
  });
  document.querySelectorAll("[data-command]").forEach(button => {
    button.addEventListener("click", () => {
      const line = button.dataset.command;
      output("kodex:" + (cwd ? "/" + cwd : "/project") + " › " + line, "command");
      execute(line);
      el.input.focus();
    });
  });
  document.getElementById("clear-terminal").addEventListener("click", () => el.output.replaceChildren());
  document.getElementById("close-preview").addEventListener("click", () => {
    el.preview.hidden = true;
    el.previewFrame.srcdoc = "";
  });
  document.getElementById("import-files").addEventListener("click", () => el.importInput.click());
  el.importInput.addEventListener("change", importFiles);
  document.getElementById("export-project").addEventListener("click", () => {
    try { exportProject(); toast("ZIP do projeto solicitado."); }
    catch (error) { toast(error.message); }
  });
  document.addEventListener("keydown", event => {
    if (event.key === "Escape") {
      el.preview.hidden = true;
      el.previewFrame.srcdoc = "";
    }
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "l") {
      event.preventDefault();
      el.output.replaceChildren();
      el.input.focus();
    }
  });

  updateStatus();
  try { saveProject(); } catch (error) { output("Aviso: " + error.message, "error"); }
  output("Kodex Project Terminal pronto.", "success");
  output("Digite help para ver os comandos. Este terminal altera somente o workspace local.");
  output("Treinamento neural real: python -m kodex_ai.train --steps 1000");
})();