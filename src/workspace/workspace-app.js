(() => {
  "use strict";

  const engine = window.KodexWorkspaceEngine;
  const STORAGE_KEY = "kodex:project-workspace:v1";
  const elements = {
    projectName: document.getElementById("project-name"),
    fileList: document.getElementById("file-list"),
    fileCount: document.getElementById("file-count"),
    activePath: document.getElementById("active-path"),
    editor: document.getElementById("code-editor"),
    gutter: document.getElementById("line-numbers"),
    editorInfo: document.getElementById("editor-info"),
    status: document.getElementById("save-status"),
    toast: document.getElementById("workspace-toast"),
    checks: document.getElementById("check-results"),
    checkSummary: document.getElementById("check-summary"),
    preview: document.getElementById("preview-shell"),
    previewFrame: document.getElementById("preview-frame"),
    importInput: document.getElementById("import-input")
  };
  let toastTimer = null;
  let state = loadWorkspace();
  let activePath = state.activePath && state.files.some(file => file.path === state.activePath)
    ? state.activePath
    : state.files[0]?.path || null;

  function loadWorkspace() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        const files = engine.collectEntries(parsed.files || []);
        if (files.length <= engine.MAX_FILES && engine.measureEntries(files) <= engine.MAX_PROJECT_BYTES) {
          return {
            name: typeof parsed.name === "string" ? parsed.name.slice(0, 80) : "Meu projeto",
            files,
            activePath: parsed.activePath || null
          };
        }
      }
    } catch {
      localStorage.removeItem(STORAGE_KEY);
    }
    return { name: "Meu projeto", files: engine.collectEntries(engine.createStarterProject()), activePath: "index.html" };
  }

  function persistWorkspace() {
    try {
      const entries = engine.collectEntries(state.files);
      if (entries.length > engine.MAX_FILES) throw new Error("O projeto ultrapassou o limite de 200 arquivos.");
      const oversized = entries.find(file => new TextEncoder().encode(file.content).byteLength > engine.MAX_FILE_BYTES);
      if (oversized) throw new Error("O arquivo " + oversized.path + " ultrapassa 512 KiB.");
      const bytes = engine.measureEntries(entries);
      if (bytes > engine.MAX_PROJECT_BYTES) throw new Error("O projeto ultrapassou 1.500 KiB de texto.");
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        schemaVersion: 1,
        name: state.name,
        activePath,
        files: entries
      }));
      setStatus("Salvo neste dispositivo · " + engine.formatBytes(bytes), "saved");
      return true;
    } catch (error) {
      setStatus("Alterações ainda não salvas", "error");
      showToast(error.message || "Não foi possível salvar no armazenamento local.");
      return false;
    }
  }

  function setStatus(message, kind = "") {
    elements.status.textContent = message;
    elements.status.dataset.state = kind;
  }

  function showToast(message) {
    elements.toast.textContent = message;
    elements.toast.hidden = false;
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      elements.toast.hidden = true;
    }, 3200);
  }

  function filesByPath() {
    return Object.fromEntries(state.files.map(file => [file.path, file.content]));
  }

  function activeFile() {
    return state.files.find(file => file.path === activePath) || null;
  }

  function extension(path) {
    const match = path.match(/\.([^.\/]+)$/);
    return match ? match[1].toLowerCase() : "txt";
  }

  function renderTree() {
    elements.fileList.replaceChildren();
    const files = [...state.files].sort((a, b) => a.path.localeCompare(b.path));
    for (const file of files) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "file-row" + (file.path === activePath ? " active" : "");
      button.setAttribute("aria-current", file.path === activePath ? "page" : "false");
      const icon = document.createElement("span");
      icon.className = "file-extension";
      icon.textContent = extension(file.path).slice(0, 4);
      const name = document.createElement("span");
      name.className = "file-path";
      name.textContent = file.path;
      name.title = file.path;
      button.append(icon, name);
      button.addEventListener("click", () => selectFile(file.path));
      elements.fileList.append(button);
    }
    elements.fileCount.textContent = String(state.files.length);
  }

  function renderLineNumbers() {
    const lineCount = Math.max(1, elements.editor.value.split("\n").length);
    elements.gutter.textContent = Array.from({ length: lineCount }, (_, index) => index + 1).join("\n");
    elements.editorInfo.textContent = lineCount + " linhas · " + engine.formatBytes(new TextEncoder().encode(elements.editor.value).length);
  }

  function renderEditor() {
    const file = activeFile();
    const hasFile = Boolean(file);
    elements.editor.disabled = !hasFile;
    elements.editor.value = file?.content || "";
    elements.activePath.textContent = file?.path || "Nenhum arquivo selecionado";
    elements.editor.placeholder = hasFile ? "" : "Crie ou importe um arquivo para começar.";
    for (const id of ["rename-file", "delete-file", "download-file", "save-file"]) {
      document.getElementById(id).disabled = !hasFile;
    }
    renderLineNumbers();
    renderTree();
  }

  function selectFile(path) {
    if (activeFile() && elements.editor.value !== activeFile().content) {
      activeFile().content = elements.editor.value;
      persistWorkspace();
    }
    activePath = path;
    state.activePath = path;
    elements.checks.hidden = true;
    renderEditor();
    setStatus("Arquivo local · " + path, "saved");
  }

  function createFile() {
    const pathInput = window.prompt("Caminho relativo do novo arquivo (ex.: src/app.js):", "src/app.js");
    if (pathInput === null) return;
    let path;
    try {
      path = engine.normalizeProjectPath(pathInput);
    } catch (error) {
      showToast(error.message);
      return;
    }
    if (state.files.some(file => file.path === path)) {
      showToast("Esse arquivo já existe.");
      return;
    }
    if (state.files.length >= engine.MAX_FILES) {
      showToast("O projeto atingiu o limite de 200 arquivos.");
      return;
    }
    state.files.push({ path, content: "" });
    activePath = path;
    state.activePath = path;
    persistWorkspace();
    renderEditor();
    elements.editor.focus();
    showToast("Arquivo criado no projeto local.");
  }

  function renameFile() {
    const file = activeFile();
    if (!file) return;
    const rawPath = window.prompt("Novo caminho relativo:", file.path);
    if (rawPath === null) return;
    let nextPath;
    try {
      nextPath = engine.normalizeProjectPath(rawPath);
    } catch (error) {
      showToast(error.message);
      return;
    }
    if (nextPath !== file.path && state.files.some(entry => entry.path === nextPath)) {
      showToast("Já existe um arquivo com esse caminho.");
      return;
    }
    file.path = nextPath;
    activePath = nextPath;
    state.activePath = nextPath;
    persistWorkspace();
    renderEditor();
    showToast("Arquivo renomeado.");
  }

  function deleteFile() {
    const file = activeFile();
    if (!file) return;
    if (!window.confirm("Excluir " + file.path + " deste projeto local? Essa ação não pode ser desfeita.")) return;
    state.files = state.files.filter(entry => entry.path !== file.path);
    activePath = state.files[0]?.path || null;
    state.activePath = activePath;
    persistWorkspace();
    renderEditor();
    showToast("Arquivo removido do armazenamento local do Kodex.");
  }

  function newProject() {
    if (!window.confirm("Criar um novo projeto de exemplo? O workspace local atual será substituído.")) return;
    state.name = "Meu projeto";
    state.files = engine.collectEntries(engine.createStarterProject());
    activePath = "index.html";
    state.activePath = activePath;
    elements.projectName.value = state.name;
    persistWorkspace();
    renderEditor();
    elements.checks.hidden = true;
    showToast("Novo projeto local criado.");
  }

  async function importFiles() {
    const chosen = Array.from(elements.importInput.files || []);
    elements.importInput.value = "";
    if (!chosen.length) return;
    const incoming = [];
    try {
      for (const file of chosen) {
        if (file.size > engine.MAX_FILE_BYTES) throw new Error(file.name + " ultrapassa 512 KiB.");
        const rawPath = file.webkitRelativePath || file.name;
        const path = engine.normalizeProjectPath(rawPath);
        const content = await file.text();
        if (content.includes("\u0000")) throw new Error(file.name + " parece ser binário; apenas arquivos de texto são importados.");
        incoming.push({ path, content });
      }
      const existing = new Set(state.files.map(file => file.path));
      const collisions = incoming.filter(file => existing.has(file.path));
      if (collisions.length && !window.confirm("Substituir estes arquivos existentes? " + collisions.map(file => file.path).join(", "))) return;
      const replacement = new Map(state.files.map(file => [file.path, file.content]));
      for (const file of incoming) replacement.set(file.path, file.content);
      const entries = engine.collectEntries(Array.from(replacement, ([path, content]) => ({ path, content })));
      if (entries.length > engine.MAX_FILES) throw new Error("O projeto ultrapassaria 200 arquivos.");
      if (engine.measureEntries(entries) > engine.MAX_PROJECT_BYTES) throw new Error("O projeto ultrapassaria 1.500 KiB de texto.");
      state.files = entries;
      activePath = incoming[incoming.length - 1].path;
      state.activePath = activePath;
      persistWorkspace();
      renderEditor();
      showToast(incoming.length + " arquivo(s) de texto importado(s).");
    } catch (error) {
      showToast(error.message || "Não foi possível importar os arquivos.");
    }
  }

  function triggerDownload(blob, filename) {
    if (/KodexAndroid/i.test(navigator.userAgent)) {
      blob.arrayBuffer().then(buffer => {
        const bytes = new Uint8Array(buffer);
        const chunks = [];
        for (let offset = 0; offset < bytes.length; offset += 0x8000) {
          chunks.push(String.fromCharCode.apply(null, bytes.subarray(offset, Math.min(offset + 0x8000, bytes.length))));
        }
        window.KodexNativePendingDownload = {
          filename: String(filename || "kodex-export").split(/[\\/]/).pop(),
          mime: blob.type.startsWith("application/zip") ? "application/zip" : "text/plain",
          base64: btoa(chunks.join(""))
        };
        setStatus("Escolha onde salvar o arquivo…", "saved");
        window.location.href = "kodex-download://save/" + encodeURIComponent(window.KodexNativePendingDownload.filename);
      }).catch(() => showToast("Não foi possível preparar o arquivo para exportação."));
      return;
    }
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    anchor.rel = "noopener";
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  window.KodexNativeDownloadComplete = (success, message) => {
    showToast(message || (success ? "Arquivo salvo." : "Exportação cancelada."));
    if (!success) setStatus("Exportação cancelada", "error");
  };

  function downloadCurrentFile() {
    const file = activeFile();
    if (!file) return;
    triggerDownload(new Blob([file.content], { type: "text/plain;charset=utf-8" }), file.path.split("/").pop());
    showToast("Download solicitado para " + file.path.split("/").pop() + ".");
  }

  function exportProject() {
    try {
      const bytes = engine.buildProjectZip(state.files);
      triggerDownload(new Blob([bytes], { type: "application/zip" }), safeFilename(state.name) + ".zip");
      showToast("ZIP criado com " + state.files.length + " arquivo(s).");
    } catch (error) {
      showToast(error.message || "Não foi possível gerar o ZIP.");
    }
  }

  function safeFilename(value) {
    return String(value || "kodex-projeto").trim().replace(/[^a-z0-9-_]+/gi, "-").replace(/^-+|-+$/g, "").slice(0, 60) || "kodex-projeto";
  }

  function previewProject() {
    try {
      elements.previewFrame.srcdoc = engine.buildPreviewHtml(filesByPath());
      elements.preview.hidden = false;
      document.getElementById("close-preview").focus();
    } catch (error) {
      showToast(error.message || "Não foi possível abrir a pré-visualização.");
    }
  }

  function closePreview() {
    elements.preview.hidden = true;
    elements.previewFrame.srcdoc = "";
  }

  function runChecks() {
    const report = engine.validateProject(filesByPath());
    elements.checks.replaceChildren();
    elements.checkSummary.textContent = report.failed
      ? report.failed + " falha(s), " + report.warnings + " aviso(s), " + report.passed + " aprovação(ões)"
      : report.warnings
        ? report.warnings + " aviso(s); " + report.passed + " checagem(ns) básica(s) aprovada(s)"
        : report.passed + " checagem(ns) básica(s) aprovada(s)";
    report.checks.forEach(check => {
      const row = document.createElement("div");
      row.className = "check-row " + check.status;
      const marker = document.createElement("span");
      marker.className = "check-marker";
      marker.textContent = check.status === "pass" ? "✓" : check.status === "warn" ? "!" : "×";
      const copy = document.createElement("div");
      copy.className = "check-copy";
      const title = document.createElement("strong");
      title.textContent = check.title;
      const detail = document.createElement("small");
      detail.textContent = check.detail;
      copy.append(title, detail);
      row.append(marker, copy);
      elements.checks.append(row);
    });
    elements.checks.hidden = false;
    elements.checks.scrollIntoView({ behavior: "smooth", block: "nearest" });
    setStatus(report.failed ? "Verificação encontrou falhas" : "Verificação estática concluída", report.failed ? "error" : "saved");
  }

  function saveCurrentFile() {
    const file = activeFile();
    if (file) file.content = elements.editor.value;
    state.activePath = activePath;
    persistWorkspace();
  }

  elements.projectName.value = state.name;
  elements.projectName.addEventListener("change", () => {
    state.name = elements.projectName.value.trim().slice(0, 80) || "Meu projeto";
    elements.projectName.value = state.name;
    persistWorkspace();
  });
  elements.editor.addEventListener("input", () => {
    const file = activeFile();
    if (!file) return;
    file.content = elements.editor.value;
    state.activePath = activePath;
    renderLineNumbers();
    persistWorkspace();
  });
  elements.editor.addEventListener("scroll", () => {
    elements.gutter.scrollTop = elements.editor.scrollTop;
  });
  elements.editor.addEventListener("keydown", event => {
    if (event.key === "Tab") {
      event.preventDefault();
      elements.editor.setRangeText("  ", elements.editor.selectionStart, elements.editor.selectionEnd, "end");
      elements.editor.dispatchEvent(new Event("input", { bubbles: true }));
    }
  });

  document.getElementById("new-file").addEventListener("click", createFile);
  document.getElementById("new-project").addEventListener("click", newProject);
  document.getElementById("import-files").addEventListener("click", () => elements.importInput.click());
  elements.importInput.addEventListener("change", importFiles);
  document.getElementById("export-zip").addEventListener("click", exportProject);
  document.getElementById("preview-project").addEventListener("click", previewProject);
  document.getElementById("close-preview").addEventListener("click", closePreview);
  document.getElementById("check-project").addEventListener("click", runChecks);
  document.getElementById("save-file").addEventListener("click", () => {
    saveCurrentFile();
    showToast("Salvamento local concluído quando indicado no status.");
  });
  document.getElementById("download-file").addEventListener("click", downloadCurrentFile);
  document.getElementById("rename-file").addEventListener("click", renameFile);
  document.getElementById("delete-file").addEventListener("click", deleteFile);
  document.addEventListener("keydown", event => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
      event.preventDefault();
      saveCurrentFile();
    }
    if (event.key === "Escape") closePreview();
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      event.preventDefault();
      previewProject();
    }
  });
  window.addEventListener("beforeunload", saveCurrentFile);

  if (!localStorage.getItem(STORAGE_KEY)) persistWorkspace();
  renderEditor();
})();