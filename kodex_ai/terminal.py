from __future__ import annotations

import argparse
import ast
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path


OUTPUT_LIMIT = 60_000
IGNORED_DIRECTORIES = {".git", ".venv", "venv", "node_modules", "__pycache__", "artifacts"}
ALLOWED_COMMANDS = (
    re.compile(r"^python(?:3)? -m kodex_ai\.(?:train|sweep|chat|prepare_data)(?:\s|$)"),
    re.compile(r"^python(?:3)? -m unittest(?:\s|$)"),
    re.compile(r"^python(?:3)? -m compileall(?:\s|$)"),
    re.compile(r"^node --test(?:\s|$)"),
    re.compile(r"^npm test$"),
    re.compile(r"^npm run check$"),
    re.compile(r"^git (?:status(?: --short)?|diff(?: --stat)?|log --oneline(?: -n [0-9]+)?|branch|show --stat(?: [a-f0-9]+)?)$"),
)


class ProjectTerminal:
    def __init__(self, root: str | Path, unsafe_shell: bool = False, timeout: int = 180):
        self.root = Path(root).resolve()
        self.cwd = self.root
        self.unsafe_shell = unsafe_shell
        self.timeout = timeout
        if not self.root.is_dir():
            raise NotADirectoryError(self.root)

    def resolve_inside(self, value: str) -> Path:
        candidate = Path(value)
        if candidate.is_absolute():
            raise ValueError("Use um caminho relativo ao projeto.")
        resolved = (self.cwd / candidate).resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as error:
            raise ValueError("O caminho tenta sair da pasta do projeto.") from error
        return resolved

    def relative(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.root)) or "."
        except ValueError:
            return "."

    def list_directory(self, value: str = ".") -> str:
        directory = self.resolve_inside(value)
        if not directory.exists():
            raise FileNotFoundError(value)
        if not directory.is_dir():
            return directory.name
        lines = []
        for item in sorted(directory.iterdir(), key=lambda child: (not child.is_dir(), child.name.casefold())):
            if item.name in IGNORED_DIRECTORIES:
                continue
            suffix = "/" if item.is_dir() else ""
            size = "" if item.is_dir() else f"  {item.stat().st_size} B"
            lines.append(f"{item.name}{suffix}{size}")
        return "\n".join(lines) if lines else "(pasta vazia)"

    def tree(self, value: str = ".", max_items: int = 200) -> str:
        directory = self.resolve_inside(value)
        if not directory.is_dir():
            raise NotADirectoryError(value)
        lines = [self.relative(directory) + "/"]
        count = 0
        for current, dirs, files in os.walk(directory):
            dirs[:] = sorted(name for name in dirs if name not in IGNORED_DIRECTORIES)
            files.sort()
            relative_current = Path(current).relative_to(directory)
            depth = len(relative_current.parts)
            for filename in files:
                if count >= max_items:
                    lines.append("… limite de itens da árvore atingido")
                    return "\n".join(lines)
                lines.append("  " * (depth + 1) + filename)
                count += 1
            if count >= max_items:
                lines.append("… limite de itens da árvore atingido")
                break
        return "\n".join(lines)

    def check(self) -> str:
        reports = []
        failures = 0
        for path in sorted(self.root.rglob("*")):
            if any(part in IGNORED_DIRECTORIES for part in path.parts) or not path.is_file():
                continue
            if path.suffix == ".py":
                try:
                    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
                    reports.append("OK Python " + self.relative(path))
                except (SyntaxError, UnicodeDecodeError) as error:
                    failures += 1
                    reports.append("FALHA Python " + self.relative(path) + ": " + str(error))
            elif path.suffix == ".json":
                try:
                    json.loads(path.read_text(encoding="utf-8"))
                    reports.append("OK JSON " + self.relative(path))
                except (json.JSONDecodeError, UnicodeDecodeError) as error:
                    failures += 1
                    reports.append("FALHA JSON " + self.relative(path) + ": " + str(error))
        reports.append(f"Checagem estática: {failures} falha(s), {len(reports) - failures - 1} arquivo(s) verificado(s).")
        reports.append("Isso não executa o programa nem substitui os testes.")
        return "\n".join(reports)

    def execute_external(self, command_line: str) -> str:
        raw = command_line.strip()
        if not raw:
            return ""
        if self.unsafe_shell:
            completed = subprocess.run(
                raw,
                cwd=self.cwd,
                shell=True,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=self.timeout,
                check=False,
            )
        else:
            if not any(pattern.fullmatch(raw) or pattern.match(raw) and raw.split()[0:2] in (["python", "-m"], ["python3", "-m"]) for pattern in ALLOWED_COMMANDS):
                allowed = "\n".join("  " + pattern.pattern.replace("^", "").replace("$", "") for pattern in ALLOWED_COMMANDS)
                raise PermissionError(
                    "Comando externo bloqueado por padrão. Prefixos permitidos:\n" + allowed
                    + "\nUse --unsafe-shell somente quando realmente quiser dar acesso ao shell completo."
                )
            argv = shlex.split(raw)
            env = os.environ.copy()
            env["PYTHONPATH"] = str(self.root) + os.pathsep + env.get("PYTHONPATH", "")
            completed = subprocess.run(
                argv,
                cwd=self.cwd,
                shell=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=max(self.timeout, 3600) if "kodex_ai.train" in raw or "kodex_ai.sweep" in raw else self.timeout,
                check=False,
                env=env,
            )
        result = completed.stdout or ""
        result += f"\n[exit code: {completed.returncode}]"
        if len(result) > OUTPUT_LIMIT:
            result = result[:OUTPUT_LIMIT] + "\n… saída truncada pelo limite do terminal."
        return result.rstrip()

    def execute(self, line: str) -> tuple[str, bool]:
        command_line = line.strip()
        if not command_line:
            return "", False
        try:
            args = shlex.split(command_line, posix=True)
        except ValueError as error:
            return "Erro ao interpretar os argumentos: " + str(error), False
        command = args[0].casefold()
        rest = args[1:]

        try:
            if command in {"exit", "quit", "sair", "logout"}:
                return "Terminal encerrado.", True
            if command in {"help", "ajuda", "?"}:
                return self.help_text(), False
            if command in {"clear", "cls", "limpar"}:
                return "\x1b[2J\x1b[H", False
            if command == "pwd":
                return self.relative(self.cwd), False
            if command == "cd":
                target = self.resolve_inside(rest[0] if rest else ".")
                if not target.is_dir():
                    return "A pasta não existe: " + self.relative(target), False
                self.cwd = target
                return self.relative(self.cwd), False
            if command in {"ls", "dir"}:
                return self.list_directory(rest[0] if rest else "."), False
            if command == "tree":
                return self.tree(rest[0] if rest else "."), False
            if command in {"cat", "type"}:
                if len(rest) != 1:
                    return "Uso: cat caminho/arquivo", False
                path = self.resolve_inside(rest[0])
                if not path.is_file():
                    return "Arquivo não encontrado: " + rest[0], False
                if path.stat().st_size > 1_000_000:
                    return "Arquivo acima de 1 MB; use um editor externo para arquivos grandes.", False
                return path.read_text(encoding="utf-8"), False
            if command == "touch":
                if len(rest) != 1:
                    return "Uso: touch caminho/arquivo", False
                path = self.resolve_inside(rest[0])
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch(exist_ok=True)
                return "Arquivo disponível: " + self.relative(path), False
            if command == "mkdir":
                if len(rest) != 1:
                    return "Uso: mkdir caminho/pasta", False
                path = self.resolve_inside(rest[0])
                path.mkdir(parents=True, exist_ok=True)
                return "Pasta criada: " + self.relative(path), False
            if command in {"write", "append"}:
                if len(rest) < 2:
                    return f"Uso: {command} caminho/arquivo \"texto com espaços\"", False
                path = self.resolve_inside(rest[0])
                path.parent.mkdir(parents=True, exist_ok=True)
                content = " ".join(rest[1:])
                mode = "a" if command == "append" else "w"
                if command == "write" and path.exists():
                    return "O arquivo já existe; use append para acrescentar conteúdo ou abra o editor do workspace para substituí-lo.", False
                with path.open(mode, encoding="utf-8") as handle:
                    handle.write(content)
                    if command == "append":
                        handle.write("\n")
                return f"{'Conteúdo acrescentado' if command == 'append' else 'Arquivo criado'}: {self.relative(path)}", False
            if command == "rm":
                if len(rest) != 1:
                    return "Uso: rm caminho/arquivo", False
                path = self.resolve_inside(rest[0])
                if not path.exists() or not path.is_file():
                    return "Arquivo não encontrado (diretórios não são removidos aqui).", False
                confirmation = input(f"Excluir permanentemente {self.relative(path)}? Digite SIM: ").strip()
                if confirmation != "SIM":
                    return "Exclusão cancelada.", False
                path.unlink()
                return "Arquivo removido: " + self.relative(path), False
            if command == "mv":
                if len(rest) != 2:
                    return "Uso: mv caminho/antigo caminho/novo", False
                source = self.resolve_inside(rest[0])
                target = self.resolve_inside(rest[1])
                if not source.is_file():
                    return "Arquivo de origem não encontrado.", False
                if target.exists():
                    return "O destino já existe; nada foi sobrescrito.", False
                target.parent.mkdir(parents=True, exist_ok=True)
                source.rename(target)
                return "Movido para " + self.relative(target), False
            if command == "grep":
                if len(rest) not in {1, 2}:
                    return "Uso: grep padrão [arquivo-ou-pasta]", False
                pattern = re.compile(rest[0], re.IGNORECASE)
                target = self.resolve_inside(rest[1] if len(rest) == 2 else ".")
                files = [target] if target.is_file() else [
                    path for path in target.rglob("*")
                    if path.is_file() and not any(part in IGNORED_DIRECTORIES for part in path.parts)
                ]
                rows = []
                for path in files:
                    try:
                        if path.stat().st_size > 1_000_000:
                            continue
                        for line_number, text in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                            if pattern.search(text):
                                rows.append(f"{self.relative(path)}:{line_number}: {text}")
                                if len(rows) >= 200:
                                    rows.append("… limite de 200 resultados atingido")
                                    return "\n".join(rows)
                    except (UnicodeDecodeError, OSError):
                        continue
                return "\n".join(rows) if rows else "Nenhuma ocorrência encontrada.", False
            if command == "wc":
                if len(rest) != 1:
                    return "Uso: wc caminho/arquivo", False
                path = self.resolve_inside(rest[0])
                text = path.read_text(encoding="utf-8")
                return f"{len(text.splitlines())} linhas  {len(text.split())} palavras  {len(text.encode('utf-8'))} bytes", False
            if command in {"check", "verificar"}:
                return self.check(), False
            if command == "run":
                return self.execute_external(command_line[command_line.find(" ") + 1 :]), False
            if command == "train":
                subcommand = rest[0] if rest else ""
                if subcommand == "run":
                    return self.execute_external("python -m kodex_ai.train " + " ".join(rest[1:])), False
                if subcommand == "chat":
                    return self.execute_external("python -m kodex_ai.chat " + " ".join(rest[1:])), False
                if subcommand == "plan":
                    return self.execute_external("python -m kodex_ai.sweep plan " + " ".join(rest[1:])), False
                if subcommand == "status":
                    return self.execute_external("python -m kodex_ai.sweep status " + " ".join(rest[1:])), False
                return "Uso: train run [opções] | train chat [opções] | train plan --trials N | train status", False
            return "Comando não reconhecido. Digite help.", False
        except (OSError, ValueError, PermissionError, subprocess.SubprocessError) as error:
            return "Erro: " + str(error), False

    @staticmethod
    def help_text() -> str:
        return """KODEX PROJECT TERMINAL

Arquivo e navegação
  pwd                         mostra a pasta de projeto atual
  ls [pasta]                  lista arquivos e pastas
  tree [pasta]                mostra a árvore do projeto
  cd [pasta]                  navega sem sair da raiz do projeto
  cat arquivo                 imprime um arquivo de texto
  touch arquivo               cria arquivo vazio
  mkdir pasta                 cria uma pasta
  write arquivo "texto"       cria arquivo novo
  append arquivo "texto"      acrescenta uma linha
  mv origem destino           move/renomeia sem sobrescrever
  rm arquivo                  pede confirmação e remove um arquivo
  grep padrão [arquivo|pasta] procura com expressão regular
  wc arquivo                  conta linhas, palavras e bytes
  check                       verifica sintaxe Python e JSON estático

Treinamento real (requer Python e PyTorch instalados)
  train run --steps 1000      treina o Transformer local e cria checkpoints
  train chat --checkpoint ... conversa com um checkpoint treinado
  train plan --trials 1000000 cria uma fila persistente de experimentos
  train status                mostra pendências/conclusões da fila

Comandos externos aprovados
  run python -m kodex_ai.train ...
  run python -m kodex_ai.sweep ...
  run python -m unittest discover -s tests
  run node --test
  run npm test
  run npm run check
  run git status
  run git diff --stat

O terminal limita escrita e navegação de arquivos à pasta do projeto por padrão.
O treinamento usa workers e hardware reais; milhões de experimentos podem ficar na fila,
mas só a quantidade de workers escolhida é executada ao mesmo tempo.
Para permitir shell arbitrário, reinicie com --unsafe-shell e confirme o aviso."""


def main() -> int:
    parser = argparse.ArgumentParser(description="Local project terminal for Kodex.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--unsafe-shell", action="store_true")
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()
    terminal = ProjectTerminal(args.root, args.unsafe_shell, args.timeout)
    if terminal.unsafe_shell:
        print("AVISO: comandos livres podem acessar e alterar arquivos fora do projeto e usar a rede.")
        phrase = input("Para habilitar shell arbitrário, digite SIM, ATIVAR SHELL LIVRE: ").strip()
        if phrase != "SIM, ATIVAR SHELL LIVRE":
            print("Modo livre cancelado.")
            terminal.unsafe_shell = False

    print("Kodex Project Terminal | " + str(terminal.root))
    print("Digite help para comandos, train plan para organizar experimentos, ou exit para sair.")
    while True:
        try:
            line = input(f"kodex:{terminal.relative(terminal.cwd)}$ ")
        except (EOFError, KeyboardInterrupt):
            print("\nTerminal encerrado.")
            break
        try:
            output, should_exit = terminal.execute(line)
        except subprocess.TimeoutExpired:
            output, should_exit = "Erro: tempo limite do comando excedido.", False
        except Exception as error:
            output, should_exit = "Erro interno do terminal: " + str(error), False
        if output == "\x1b[2J\x1b[H":
            print(output, end="")
        elif output:
            print(output)
        if should_exit:
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
