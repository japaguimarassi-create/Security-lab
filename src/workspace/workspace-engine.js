(() => {
  "use strict";

  const MAX_FILES = 200;
  const MAX_FILE_BYTES = 512 * 1024;
  const MAX_PROJECT_BYTES = 1500 * 1024;
  const encoder = new TextEncoder();

  function normalizeProjectPath(value) {
    if (typeof value !== "string") throw new Error("O caminho do arquivo precisa ser texto.");
    let path = value.trim().replace(/\\/g, "/");
    while (path.startsWith("./")) path = path.slice(2);
    if (!path || path.startsWith("/") || /^[a-z]:/i.test(path) || /[\u0000-\u001f\u007f]/.test(path)) {
      throw new Error("Use um caminho relativo, como src/app.js.");
    }
    const parts = path.split("/");
    if (parts.some(part => !part || part === "." || part === ".." || part.length > 120)) {
      throw new Error("O caminho tem uma parte vazia ou inválida. Caminhos com .. não são aceitos.");
    }
    if (path.length > 240) throw new Error("O caminho é longo demais (máximo: 240 caracteres).");
    return parts.join("/");
  }

  function collectEntries(files) {
    const pairs = Array.isArray(files)
      ? files.map(file => [file.path, file.content])
      : files && typeof files === "object"
        ? Object.entries(files)
        : [];
    const seen = new Set();
    return pairs.map(([rawPath, rawContent]) => {
      const path = normalizeProjectPath(rawPath);
      if (seen.has(path)) throw new Error("Caminho duplicado: " + path);
      seen.add(path);
      if (typeof rawContent !== "string") throw new Error("O conteúdo de " + path + " precisa ser texto.");
      return { path, content: rawContent };
    });
  }

  function measureEntries(entries) {
    return entries.reduce((sum, entry) => sum + encoder.encode(entry.content).byteLength, 0);
  }

  function createStarterProject() {
    return {
      "README.md": "# Meu primeiro projeto\n\nProjeto local de exemplo criado pelo Kodex.\n\n- Edite os arquivos na área de trabalho.\n- Use Verificar para executar checagens estáticas básicas.\n- Use Pré-visualizar para abrir o HTML em um quadro isolado.\n- Exporte um ZIP para guardar os arquivos fora do armazenamento local.\n\nA pré-visualização não é um ambiente de produção nem um compilador.",
      "index.html": `<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Meu projeto</title>
  <link rel="stylesheet" href="./styles.css">
</head>
<body>
  <main class="card">
    <p class="eyebrow">MEU PRIMEIRO PROJETO</p>
    <h1>Olá, mundo.</h1>
    <p>Edite este arquivo, os estilos ou o JavaScript no Kodex.</p>
    <button id="counter-button" type="button">Cliques: <span id="counter">0</span></button>
  </main>
  <script src="./app.js"></script>
</body>
</html>`,
      "styles.css": `:root {
  color-scheme: light;
  font-family: system-ui, sans-serif;
  background: #f2f4f8;
  color: #192235;
}
body {
  min-height: 100vh;
  display: grid;
  place-items: center;
  margin: 0;
}
.card {
  width: min(560px, calc(100% - 40px));
  padding: 32px;
  border: 1px solid #d9dfeb;
  border-radius: 18px;
  background: white;
  box-shadow: 0 16px 45px #23375c18;
}
.eyebrow { color: #4367b2; font-size: 12px; font-weight: 700; letter-spacing: .12em; }
h1 { margin-bottom: 8px; }
button { border: 0; border-radius: 10px; padding: 12px 16px; background: #264ca2; color: white; font: inherit; }
`,
      "app.js": `const button = document.querySelector("#counter-button");
const counter = document.querySelector("#counter");
let clicks = 0;

button.addEventListener("click", () => {
  clicks += 1;
  counter.textContent = String(clicks);
});`
    };
  }

  function validateProject(files) {
    let entries;
    try {
      entries = collectEntries(files);
    } catch (error) {
      return {
        checks: [{ id: "paths", status: "fail", title: "Caminhos dos arquivos", detail: error.message }],
        passed: 0,
        warnings: 0,
        failed: 1,
        total: 1,
        byteLength: 0
      };
    }
    const checks = [];
    const add = (id, status, title, detail) => checks.push({ id, status, title, detail });
    const totalBytes = measureEntries(entries);
    const pathSafe = entries.length <= MAX_FILES && entries.every(file => {
      try {
        return normalizeProjectPath(file.path) === file.path;
      } catch {
        return false;
      }
    });
    add("paths", pathSafe ? "pass" : "fail", "Caminhos e quantidade",
      pathSafe ? entries.length + " arquivo(s); caminhos relativos válidos." : "Limite de arquivos excedido ou caminho inválido.");
    const sizesSafe = entries.every(file => encoder.encode(file.content).byteLength <= MAX_FILE_BYTES) && totalBytes <= MAX_PROJECT_BYTES;
    add("sizes", sizesSafe ? "pass" : "fail", "Tamanho do projeto",
      sizesSafe ? formatBytes(totalBytes) + " usados; dentro dos limites locais." : "Cada arquivo deve ter até 512 KiB e o projeto até 1.500 KiB.");
    if (!entries.length) {
      add("contents", "warn", "Conteúdo", "O projeto está vazio.");
    } else {
      add("contents", "pass", "Conteúdo", entries.length + " arquivo(s) de texto disponíveis para edição.");
    }

    for (const entry of entries) {
      const lower = entry.path.toLowerCase();
      if (lower.endsWith(".json")) {
        try {
          JSON.parse(entry.content);
          add("json:" + entry.path, "pass", entry.path, "JSON válido.");
        } catch (error) {
          add("json:" + entry.path, "fail", entry.path, "JSON inválido: " + error.message);
        }
      } else if (/\.(js|cjs|mjs)$/.test(lower)) {
        if (/^\s*(?:import\s|export\s)/m.test(entry.content)) {
          add("js:" + entry.path, "warn", entry.path, "Parece usar módulos ES; a checagem local não compila imports/exports.");
        } else {
          try {
            new Function(entry.content);
            add("js:" + entry.path, "pass", entry.path, "Sintaxe JavaScript clássica compilada para checagem; o código não foi executado.");
          } catch (error) {
            add("js:" + entry.path, "fail", entry.path, "Erro de sintaxe JavaScript: " + error.message);
          }
        }
      } else if (/\.(html|htm)$/.test(lower)) {
        const wellFormed = /<html[\s>]/i.test(entry.content) && /<\/html\s*>/i.test(entry.content);
        add("html:" + entry.path, wellFormed ? "pass" : "warn", entry.path,
          wellFormed ? "Estrutura HTML básica encontrada." : "Verifique manualmente a estrutura HTML.");
      }
    }
    const passed = checks.filter(check => check.status === "pass").length;
    const warnings = checks.filter(check => check.status === "warn").length;
    const failed = checks.filter(check => check.status === "fail").length;
    return { checks, passed, warnings, failed, total: checks.length, byteLength: totalBytes };
  }

  function formatBytes(bytes) {
    if (bytes < 1024) return bytes + " B";
    return (bytes / 1024).toFixed(1) + " KiB";
  }

  const crcTable = (() => {
    const table = new Uint32Array(256);
    for (let n = 0; n < 256; n += 1) {
      let c = n;
      for (let k = 0; k < 8; k += 1) c = (c & 1) ? (0xedb88320 ^ (c >>> 1)) : (c >>> 1);
      table[n] = c >>> 0;
    }
    return table;
  })();

  function crc32(bytes) {
    let crc = 0xffffffff;
    for (let i = 0; i < bytes.length; i += 1) crc = crcTable[(crc ^ bytes[i]) & 0xff] ^ (crc >>> 8);
    return (crc ^ 0xffffffff) >>> 0;
  }

  function write16(view, offset, value) {
    view.setUint16(offset, value, true);
  }

  function write32(view, offset, value) {
    view.setUint32(offset, value >>> 0, true);
  }

  function buildProjectZip(files) {
    const entries = collectEntries(files).sort((a, b) => a.path.localeCompare(b.path));
    if (entries.length > 65535) throw new Error("O ZIP não pode conter mais de 65.535 arquivos.");
    const projectBytes = measureEntries(entries);
    if (projectBytes > 8 * 1024 * 1024) throw new Error("O ZIP excede o limite de 8 MiB.");
    const chunks = [];
    const centralEntries = [];
    let offset = 0;
    const fixedDate = ((2026 - 1980) << 9) | (10 << 5) | 1;

    for (const entry of entries) {
      const name = encoder.encode(entry.path);
      const data = encoder.encode(entry.content);
      const crc = crc32(data);
      const header = new Uint8Array(30);
      const view = new DataView(header.buffer);
      write32(view, 0, 0x04034b50);
      write16(view, 4, 20);
      write16(view, 6, 0x0800);
      write16(view, 8, 0);
      write16(view, 10, 0);
      write16(view, 12, fixedDate);
      write32(view, 14, crc);
      write32(view, 18, data.length);
      write32(view, 22, data.length);
      write16(view, 26, name.length);
      write16(view, 28, 0);
      chunks.push(header, name, data);
      centralEntries.push({ name, crc, size: data.length, offset });
      offset += header.length + name.length + data.length;
    }

    const centralStart = offset;
    for (const entry of centralEntries) {
      const header = new Uint8Array(46);
      const view = new DataView(header.buffer);
      write32(view, 0, 0x02014b50);
      write16(view, 4, 20);
      write16(view, 6, 20);
      write16(view, 8, 0x0800);
      write16(view, 10, 0);
      write16(view, 12, 0);
      write16(view, 14, fixedDate);
      write32(view, 16, entry.crc);
      write32(view, 20, entry.size);
      write32(view, 24, entry.size);
      write16(view, 28, entry.name.length);
      write16(view, 30, 0);
      write16(view, 32, 0);
      write16(view, 34, 0);
      write16(view, 36, 0);
      write32(view, 38, 0);
      write32(view, 42, entry.offset);
      chunks.push(header, entry.name);
      offset += header.length + entry.name.length;
    }

    const centralSize = offset - centralStart;
    const end = new Uint8Array(22);
    const view = new DataView(end.buffer);
    write32(view, 0, 0x06054b50);
    write16(view, 4, 0);
    write16(view, 6, 0);
    write16(view, 8, entries.length);
    write16(view, 10, entries.length);
    write32(view, 12, centralSize);
    write32(view, 16, centralStart);
    write16(view, 20, 0);
    chunks.push(end);

    const totalLength = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
    if (totalLength > 0xffffffff) throw new Error("ZIP excede o tamanho máximo suportado.");
    const output = new Uint8Array(totalLength);
    let cursor = 0;
    for (const chunk of chunks) {
      output.set(chunk, cursor);
      cursor += chunk.length;
    }
    return output;
  }

  function resolveRelativePath(basePath, requestedPath) {
    const clean = String(requestedPath || "").split(/[?#]/, 1)[0];
    if (!clean || clean.startsWith("/") || /^[a-z]+:/i.test(clean) || clean.startsWith("//")) return null;
    const baseDir = basePath.includes("/") ? basePath.slice(0, basePath.lastIndexOf("/") + 1) : "";
    try {
      return normalizeProjectPath(baseDir + clean);
    } catch {
      return null;
    }
  }

  function buildPreviewHtml(files) {
    const entries = collectEntries(files);
    const byPath = Object.fromEntries(entries.map(entry => [entry.path, entry.content]));
    let html = byPath["index.html"] || "";
    if (!html) throw new Error("Crie ou importe um arquivo index.html para pré-visualizar.");
    html = html.replace(/<link\b[^>]*>/gi, tag => {
      if (!/\brel\s*=\s*["']?stylesheet["']?/i.test(tag)) return tag;
      const match = tag.match(/\bhref\s*=\s*["']([^"']+)["']/i) || tag.match(/\bhref\s*=\s*([^\s>]+)/i);
      if (!match) return tag;
      const path = resolveRelativePath("index.html", match[1]);
      if (!path || !Object.prototype.hasOwnProperty.call(byPath, path)) return "";
      return "<style>\n" + byPath[path].replace(/<\/style/gi, "<\\/style") + "\n</style>";
    });
    html = html.replace(/<script\b([^>]*)src\s*=\s*["']([^"']+)["']([^>]*)>\s*<\/script\s*>/gi, (whole, before, src, after) => {
      const path = resolveRelativePath("index.html", src);
      if (!path || !Object.prototype.hasOwnProperty.call(byPath, path)) return "";
      const moduleType = /\btype\s*=\s*["']module["']/i.test(before + after) ? ' type="module"' : "";
      return "<script" + moduleType + ">\n" + byPath[path].replace(/<\/script/gi, "<\\/script") + "\n</script>";
    });
    const csp = `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data: blob:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-src 'none'; font-src 'none'; media-src 'none'">`;
    if (/<head\b[^>]*>/i.test(html)) html = html.replace(/<head\b[^>]*>/i, match => match + csp);
    else html = csp + html;
    return html;
  }

  window.KodexWorkspaceEngine = {
    MAX_FILES,
    MAX_FILE_BYTES,
    MAX_PROJECT_BYTES,
    normalizeProjectPath,
    collectEntries,
    measureEntries,
    createStarterProject,
    validateProject,
    formatBytes,
    crc32,
    buildProjectZip,
    buildPreviewHtml
  };
})();