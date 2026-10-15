const STORAGE_KEY = "kodex:chat-threads:v2";
const MAX_THREADS = 30;
const MODES = {
  plan: {
    title: "Planejar",
    description: "Organize a abordagem antes de alterar o projeto.",
    hint: "Planejamento local"
  },
  build: {
    title: "Construir",
    description: "Prepare uma tarefa verificável para implementação.",
    hint: "Preparação de tarefa"
  }
};

const elements = {
  sidebar: document.getElementById("sidebar"),
  scrim: document.getElementById("drawer-scrim"),
  threadList: document.getElementById("thread-list"),
  threadSearch: document.getElementById("thread-search"),
  currentTitle: document.getElementById("current-title"),
  welcome: document.getElementById("welcome-state"),
  messageList: document.getElementById("message-list"),
  conversation: document.getElementById("conversation"),
  input: document.getElementById("message-input"),
  form: document.getElementById("chat-form"),
  send: document.getElementById("send-button"),
  modeDescription: document.getElementById("mode-description"),
  composerHint: document.getElementById("composer-hint"),
  contextButton: document.getElementById("context-button"),
  messageCount: document.getElementById("message-count"),
  panelMode: document.getElementById("panel-mode"),
  taskCount: document.getElementById("task-count"),
  nextStep: document.getElementById("next-step"),
  toast: document.getElementById("toast")
};

let activeMode = "plan";
let includeProjectContext = false;
let toastTimer = null;
let threads = loadThreads();
let activeThreadId = threads[0]?.id ?? null;

function loadThreads() {
  try {
    const value = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
    if (!Array.isArray(value)) return [];
    return value.filter(thread =>
      thread && typeof thread.id === "string" &&
      typeof thread.title === "string" &&
      Array.isArray(thread.messages)
    ).slice(0, MAX_THREADS);
  } catch {
    return [];
  }
}

function saveThreads() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(threads.slice(0, MAX_THREADS)));
  } catch {
    showToast("Não foi possível persistir o histórico neste dispositivo.");
  }
}

function newId() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
}

function activeThread() {
  return threads.find(thread => thread.id === activeThreadId) || null;
}

function makeThread() {
  const thread = {
    id: newId(),
    title: "Novo chat",
    mode: activeMode,
    createdAt: new Date().toISOString(),
    messages: [],
    taskCount: 0,
    nextStep: null
  };
  threads.unshift(thread);
  threads = threads.slice(0, MAX_THREADS);
  activeThreadId = thread.id;
  saveThreads();
  renderAll();
  closeSidebar();
  elements.input.focus();
}

function showToast(message) {
  elements.toast.textContent = message;
  elements.toast.hidden = false;
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    elements.toast.hidden = true;
  }, 2600);
}

function escapeText(value) {
  return String(value ?? "");
}

function formatTime(value) {
  try {
    return new Intl.DateTimeFormat("pt-BR", { hour: "2-digit", minute: "2-digit" }).format(new Date(value));
  } catch {
    return "";
  }
}

function shorten(value, limit = 39) {
  const clean = value.replace(/\s+/g, " ").trim();
  return clean.length > limit ? clean.slice(0, limit - 1) + "…" : clean;
}

function renderThreadList() {
  const query = elements.threadSearch.value.trim().toLocaleLowerCase("pt-BR");
  const visible = threads.filter(thread => thread.title.toLocaleLowerCase("pt-BR").includes(query));
  elements.threadList.replaceChildren();
  if (!visible.length) {
    const empty = document.createElement("div");
    empty.className = "thread-empty";
    empty.textContent = threads.length ? "Nenhuma conversa encontrada." : "Suas conversas aparecerão aqui.";
    elements.threadList.append(empty);
    return;
  }
  visible.forEach(thread => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "thread-item" + (thread.id === activeThreadId ? " active" : "");
    const symbol = document.createElement("span");
    symbol.className = "thread-symbol";
    symbol.textContent = thread.mode === "build" ? "⌘" : "☷";
    const title = document.createElement("span");
    title.className = "thread-name";
    title.textContent = thread.title;
    const mode = document.createElement("span");
    mode.className = "thread-mode";
    mode.textContent = thread.mode === "build" ? "Construir" : "Planejar";
    button.append(symbol, title, mode);
    button.addEventListener("click", () => {
      activeThreadId = thread.id;
      activeMode = thread.mode || "plan";
      renderAll();
      closeSidebar();
    });
    elements.threadList.append(button);
  });
}

function addSection(container, title, items, ordered = false) {
  const section = document.createElement("section");
  section.className = "response-section";
  const heading = document.createElement("h3");
  heading.textContent = title;
  const list = document.createElement(ordered ? "ol" : "ul");
  items.forEach(item => {
    const li = document.createElement("li");
    li.textContent = item;
    list.append(li);
  });
  section.append(heading, list);
  container.append(section);
}

function makeLocalPlan(prompt) {
  const text = prompt.toLocaleLowerCase("pt-BR");
  const ui = /interface|ui|tela|visual|design|layout|chat|botão|mobile/.test(text);
  const bug = /bug|erro|falha|quebrad|corrig|crash|problema/.test(text);
  const test = /teste|testes|cobertura|validar|qualidade/.test(text);
  const security = /seguran|autentica|login|permiss|token|senha|malware/.test(text);
  const data = /banco|dados|persist|histórico|salvar|armazen/.test(text);
  const steps = [];
  if (bug) steps.push("Reproduzir o comportamento e registrar o resultado atual antes de alterar o código.");
  else steps.push("Definir o comportamento esperado e os limites explícitos do escopo.");
  if (ui) steps.push("Mapear estados da interface, hierarquia visual, acessibilidade e comportamento em telas pequenas.");
  else if (security) steps.push("Desenhar limites de confiança, permissões mínimas e tratamento seguro de entradas.");
  else if (data) steps.push("Definir o formato dos dados, persistência, migração e tratamento de falhas.");
  else steps.push("Identificar os módulos envolvidos e separar responsabilidades para manter a mudança localizada.");
  steps.push("Implementar em incrementos pequenos, mantendo o comportamento existente que não faz parte da mudança.");
  if (test || bug) steps.push("Criar casos positivos, negativos e de regressão; executar os testes relevantes.");
  else steps.push("Definir verificações reproduzíveis para o caminho principal e os casos de borda.");
  steps.push("Revisar o diff, documentar limitações e confirmar os critérios de aceite.");
  const criteria = [
    "O resultado corresponde ao comportamento descrito, sem funcionalidades extras implícitas.",
    "Entradas inválidas e estados de erro têm tratamento definido.",
    "As verificações são reproduzíveis e o resultado final pode ser revisado."
  ];
  const risks = [];
  if (security) risks.push("Não armazenar segredos em arquivos do cliente nem ampliar permissões sem necessidade.");
  if (data) risks.push("Evitar perda de dados existentes e prever falhas de gravação.");
  if (ui) risks.push("Conferir teclado, contraste, texto longo e viewport móvel.");
  if (bug) risks.push("Não mascarar o sintoma; confirmar a causa com uma reprodução mínima.");
  if (!risks.length) risks.push("A falta de contexto real do repositório pode tornar incompleta a lista de arquivos afetados.");
  return {
    kind: "plan",
    title: "Plano inicial",
    intro: "Organizei um primeiro roteiro para este pedido. Ele é um rascunho heurístico local, não uma resposta gerada por um modelo treinado.",
    sections: [
      { title: "Objetivo", items: [shorten(prompt, 180)] },
      { title: "Sequência proposta", items: steps },
      { title: "Critérios de aceite", items: criteria },
      { title: "Riscos a verificar", items: risks }
    ],
    action: "Enviar este pedido para Construir"
  };
}

function makeBuildBrief(prompt) {
  const text = prompt.toLocaleLowerCase("pt-BR");
  const suggestedFiles = [];
  if (/interface|ui|tela|visual|design|layout|chat|mobile/.test(text)) suggestedFiles.push("Interface e estilos da tela afetada");
  if (/teste|testes|bug|erro|falha|corrig/.test(text)) suggestedFiles.push("Testes de regressão e cenários de erro");
  if (/banco|dados|persist|salvar|armazen|histórico/.test(text)) suggestedFiles.push("Camada responsável pelos dados e persistência");
  if (/seguran|autentica|login|permiss|token|senha/.test(text)) suggestedFiles.push("Autenticação, validações e regras de acesso");
  if (!suggestedFiles.length) suggestedFiles.push("Módulo principal da funcionalidade", "Testes relacionados e documentação");
  return {
    kind: "build",
    title: "Brief de implementação",
    intro: "A solicitação foi organizada como uma tarefa revisável. Esta versão ainda não consegue alterar arquivos nem executar comandos: o modelo generativo e o executor não estão conectados.",
    sections: [
      { title: "Resultado solicitado", items: [shorten(prompt, 180)] },
      { title: "Áreas a inspecionar", items: suggestedFiles },
      { title: "Checklist de execução", items: [
        "Ler os arquivos reais afetados e confirmar o escopo antes de editar.",
        "Implementar a menor mudança que satisfaça os critérios.",
        "Executar testes, revisar o diff e registrar os resultados reais."
      ] }
    ],
    checklist: [
      "Contexto e arquivos revisados",
      "Alteração implementada",
      "Testes executados e revisados",
      "Diff final aprovado"
    ],
    action: "Copiar brief de implementação"
  };
}

function makeResponse(prompt, mode) {
  return mode === "build" ? makeBuildBrief(prompt) : makeLocalPlan(prompt);
}

function appendMessage(thread, message) {
  thread.messages.push(message);
  if (thread.messages.length === 1 && message.role === "user") {
    thread.title = shorten(message.text, 42) || "Novo chat";
  }
}

function renderResponseBody(message, node) {
  const intro = document.createElement("p");
  intro.className = "assistant-intro";
  intro.textContent = message.intro;
  node.append(intro);

  const disclosure = document.createElement("div");
  disclosure.className = "response-disclosure";
  const lead = document.createElement("strong");
  lead.textContent = message.kind === "build" ? "Estado: aguardando runtime" : "Estado: plano preliminar";
  disclosure.append(lead, document.createTextNode(message.kind === "build"
    ? " · Nenhum arquivo foi alterado e nenhum comando foi executado."
    : " · Use como estrutura inicial; os arquivos do projeto não foram lidos pelo chat."));
  node.append(disclosure);

  (message.sections || []).forEach(section => addSection(node, section.title, section.items, section.title === "Sequência proposta"));
  if (Array.isArray(message.checklist)) {
    const checklist = document.createElement("div");
    checklist.className = "task-checklist";
    const title = document.createElement("div");
    title.className = "task-checklist-title";
    title.textContent = "CHECKLIST DA TAREFA";
    checklist.append(title);
    message.checklist.forEach((label, index) => {
      const row = document.createElement("label");
      const input = document.createElement("input");
      input.type = "checkbox";
      input.checked = Boolean(message.checkedItems?.[index]);
      input.addEventListener("change", () => {
        message.checkedItems = message.checkedItems || [];
        message.checkedItems[index] = input.checked;
        const thread = activeThread();
        if (thread) saveThreads();
        updateWorkPanel();
      });
      const text = document.createElement("span");
      text.textContent = label;
      row.append(input, text);
      checklist.append(row);
    });
    node.append(checklist);
  }
}

function renderMessage(message, index) {
  const wrapper = document.createElement("article");
  wrapper.className = "message " + (message.role === "user" ? "user" : "assistant");
  const head = document.createElement("div");
  head.className = "message-head";
  const mark = document.createElement("span");
  mark.className = "message-mark";
  mark.textContent = message.role === "user" ? "U" : "K";
  const author = document.createElement("span");
  author.textContent = message.role === "user" ? "Você" : "Kodex";
  const time = document.createElement("span");
  time.className = "message-time";
  time.textContent = formatTime(message.createdAt);
  head.append(mark, author, time);

  const bubble = document.createElement("div");
  bubble.className = "message-bubble";
  if (message.role === "user") {
    bubble.textContent = message.text;
  } else if (message.kind === "plan" || message.kind === "build") {
    renderResponseBody(message, bubble);
    const actions = document.createElement("div");
    actions.className = "response-actions";
    if (message.kind === "plan") {
      const promote = document.createElement("button");
      promote.className = "text-action primary";
      promote.type = "button";
      promote.textContent = "↗ " + message.action;
      promote.addEventListener("click", () => {
        activeMode = "build";
        renderMode();
        elements.input.value = message.sourcePrompt || "";
        autoResizeInput();
        elements.input.focus();
      });
      actions.append(promote);
    }
    const copy = document.createElement("button");
    copy.className = "text-action";
    copy.type = "button";
    copy.textContent = "⧉ Copiar";
    copy.addEventListener("click", () => copyText(buildPlainText(message), "Conteúdo copiado."));
    actions.append(copy);
    bubble.append(actions);
  } else {
    bubble.textContent = escapeText(message.text);
  }
  wrapper.append(head, bubble);
  return wrapper;
}

function buildPlainText(message) {
  const lines = [message.title || "Kodex", "", message.intro || ""];
  (message.sections || []).forEach(section => {
    lines.push("", section.title);
    section.items.forEach(item => lines.push("- " + item));
  });
  if (message.checklist) {
    lines.push("", "Checklist");
    message.checklist.forEach(item => lines.push("- [ ] " + item));
  }
  return lines.join("\n");
}

function renderConversation() {
  const thread = activeThread();
  const messages = thread?.messages || [];
  elements.welcome.hidden = messages.length > 0;
  elements.messageList.replaceChildren();
  messages.forEach((message, index) => elements.messageList.append(renderMessage(message, index)));
  elements.currentTitle.textContent = thread?.title || "Novo chat";
  elements.messageCount.textContent = String(messages.length);
  requestAnimationFrame(() => {
    elements.conversation.scrollTop = elements.conversation.scrollHeight;
  });
}

function updateWorkPanel() {
  const thread = activeThread();
  const messages = thread?.messages || [];
  const tasks = messages.filter(message => message.role === "assistant" && message.kind === "build");
  elements.messageCount.textContent = String(messages.length);
  elements.taskCount.textContent = String(tasks.length);
  elements.panelMode.textContent = MODES[activeMode].title;
  const latest = tasks[tasks.length - 1];
  elements.nextStep.replaceChildren();
  const icon = document.createElement("span");
  icon.className = "next-step-icon";
  icon.textContent = latest ? "◷" : "○";
  const copy = document.createElement("span");
  const title = document.createElement("strong");
  title.textContent = latest ? "Aguardando executor de código" : "Nenhum trabalho preparado";
  const detail = document.createElement("small");
  detail.textContent = latest ? "O brief está no histórico; nada foi executado." : "Envie uma mensagem para iniciar.";
  copy.append(title, detail);
  elements.nextStep.append(icon, copy);
}

function renderMode() {
  document.querySelectorAll("[data-mode]").forEach(button => {
    button.classList.toggle("active", button.dataset.mode === activeMode);
    button.setAttribute("aria-pressed", String(button.dataset.mode === activeMode));
  });
  elements.modeDescription.textContent = MODES[activeMode].description;
  elements.composerHint.textContent = MODES[activeMode].hint;
  elements.panelMode.textContent = MODES[activeMode].title;
  const placeholder = activeMode === "plan"
    ? "Descreva o objetivo, a ideia ou o problema que quer organizar…"
    : "Descreva a mudança que quer preparar para implementação…";
  elements.input.placeholder = placeholder;
}

function renderAll() {
  renderThreadList();
  renderMode();
  renderConversation();
  updateWorkPanel();
}

function autoResizeInput() {
  elements.input.style.height = "auto";
  elements.input.style.height = Math.min(elements.input.scrollHeight, window.innerWidth <= 720 ? 140 : 190) + "px";
}

function sendMessage(event) {
  event.preventDefault();
  const text = elements.input.value.trim();
  if (!text) return;
  if (!activeThread()) {
    const thread = {
      id: newId(),
      title: "Novo chat",
      mode: activeMode,
      createdAt: new Date().toISOString(),
      messages: [],
      taskCount: 0,
      nextStep: null
    };
    threads.unshift(thread);
    activeThreadId = thread.id;
  }
  const thread = activeThread();
  thread.mode = activeMode;
  const prompt = includeProjectContext
    ? text + "\n\nContexto disponível nesta versão: projeto Security-lab, branch kodex-programming-ai. O conteúdo real dos arquivos não foi carregado pelo chat."
    : text;
  appendMessage(thread, { role: "user", text, createdAt: new Date().toISOString(), mode: activeMode });
  const response = makeResponse(prompt, activeMode);
  response.role = "assistant";
  response.sourcePrompt = text;
  response.createdAt = new Date().toISOString();
  response.checkedItems = [];
  appendMessage(thread, response);
  if (response.kind === "build") {
    thread.taskCount = (thread.taskCount || 0) + 1;
    thread.nextStep = "Aguardando executor";
  }
  thread.mode = activeMode;
  elements.input.value = "";
  autoResizeInput();
  saveThreads();
  renderAll();
}

function openSidebar() {
  elements.sidebar.classList.add("open");
  elements.scrim.hidden = false;
}

function closeSidebar() {
  elements.sidebar.classList.remove("open");
  elements.scrim.hidden = true;
}

async function copyText(text, successMessage) {
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text);
    } else {
      const temporary = document.createElement("textarea");
      temporary.value = text;
      temporary.style.position = "fixed";
      temporary.style.opacity = "0";
      document.body.append(temporary);
      temporary.select();
      const ok = document.execCommand("copy");
      temporary.remove();
      if (!ok) throw new Error("copy unavailable");
    }
    showToast(successMessage);
  } catch {
    showToast("Cópia automática indisponível neste contexto.");
  }
}

function copyCurrentThread() {
  const thread = activeThread();
  if (!thread || !thread.messages.length) {
    showToast("Esta conversa ainda está vazia.");
    return;
  }
  const text = thread.messages.map(message => {
    if (message.role === "user") return "Você:\n" + message.text;
    return "Kodex:\n" + (message.kind ? buildPlainText(message) : message.text);
  }).join("\n\n---\n\n");
  copyText(text, "Conversa copiada.");
}

function setContext() {
  includeProjectContext = !includeProjectContext;
  elements.contextButton.setAttribute("aria-pressed", String(includeProjectContext));
  elements.contextButton.innerHTML = includeProjectContext
    ? '<span aria-hidden="true">✓</span> Contexto incluído <span class="context-chevron">⌄</span>'
    : '<span aria-hidden="true">＋</span> Contexto do projeto <span class="context-chevron">⌄</span>';
  showToast(includeProjectContext
    ? "Será anexado apenas o nome do projeto e da branch, não os arquivos."
    : "Contexto do projeto removido.");
}

document.getElementById("new-chat").addEventListener("click", makeThread);
document.getElementById("top-new-chat").addEventListener("click", makeThread);
document.getElementById("open-sidebar").addEventListener("click", openSidebar);
document.getElementById("close-sidebar").addEventListener("click", closeSidebar);
elements.scrim.addEventListener("click", closeSidebar);
elements.threadSearch.addEventListener("input", renderThreadList);
elements.form.addEventListener("submit", sendMessage);
elements.input.addEventListener("input", autoResizeInput);
elements.input.addEventListener("keydown", event => {
  if (event.key === "Enter" && !event.shiftKey && window.innerWidth > 550) {
    event.preventDefault();
    elements.form.requestSubmit();
  }
});
document.querySelectorAll("[data-mode]").forEach(button => {
  button.addEventListener("click", () => {
    activeMode = button.dataset.mode;
    const thread = activeThread();
    if (thread) thread.mode = activeMode;
    saveThreads();
    renderAll();
  });
});
document.querySelectorAll("[data-prompt]").forEach(button => {
  button.addEventListener("click", () => {
    elements.input.value = button.dataset.prompt;
    autoResizeInput();
    elements.input.focus();
  });
});
elements.contextButton.addEventListener("click", setContext);
document.getElementById("copy-thread").addEventListener("click", copyCurrentThread);
document.getElementById("copy-branch").addEventListener("click", () => copyText("kodex-programming-ai", "Branch copiada."));
document.getElementById("close-panel").addEventListener("click", () => showToast("O painel de contexto é fixo nesta versão para desktop."));
document.addEventListener("keydown", event => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
    event.preventDefault();
    makeThread();
  }
  if (event.key === "Escape") closeSidebar();
});
window.addEventListener("resize", () => {
  if (window.innerWidth > 720) closeSidebar();
});

if (!activeThreadId) {
  activeThreadId = null;
}
renderAll();