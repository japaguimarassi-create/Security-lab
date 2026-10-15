from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from kodex_ai.terminal import ProjectTerminal


class ProjectTerminalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.terminal = ProjectTerminal(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_file_commands_create_append_read_and_search_real_files(self):
        output, exit_requested = self.terminal.execute('write src/main.py "print(1)"')
        self.assertIn("Arquivo criado", output)
        self.assertFalse(exit_requested)
        output, _ = self.terminal.execute('append src/main.py "print(2)"')
        self.assertIn("acrescentado", output)
        output, _ = self.terminal.execute("cat src/main.py")
        self.assertEqual(output.rstrip("\n"), "print(1)\nprint(2)")
        output, _ = self.terminal.execute("grep print src/main.py")
        self.assertIn("src/main.py:1", output)
        self.assertIn("src/main.py:2", output)

    def test_path_traversal_is_rejected(self):
        output, _ = self.terminal.execute("touch ../outside.txt")
        self.assertIn("Erro", output)
        self.assertFalse((self.root.parent / "outside.txt").exists())

    def test_external_shell_is_denied_without_explicit_opt_in(self):
        output, _ = self.terminal.execute('run python -c "print(123)"')
        self.assertIn("bloqueado por padrão", output)

    def test_approved_test_command_is_not_rejected_by_the_allowlist(self):
        output, _ = self.terminal.execute("run npm run check")
        self.assertNotIn("bloqueado por padrão", output)
        self.assertIn("[exit code:", output)

    def test_cd_cannot_escape_project_root(self):
        output, _ = self.terminal.execute("cd ..")
        self.assertIn("Erro", output)
        self.assertEqual(self.terminal.cwd, self.root)

    def test_unknown_command_is_not_executed(self):
        output, should_exit = self.terminal.execute("curl https://example.com")
        self.assertIn("não reconhecido", output)
        self.assertFalse(should_exit)


if __name__ == "__main__":
    unittest.main()
