"""Offline parity and synthetic regression checks; never contact production."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
DEPLOY = ROOT / "deployment/youit"


class SnapshotTests(unittest.TestCase):
    def test_every_copied_file_matches_server_hash(self):
        manifest = json.loads((DEPLOY / "server-patches.sha256.json").read_text())
        self.assertEqual(len(manifest["files"]), 29)
        for entry in manifest["files"]:
            with self.subTest(path=entry["path"]):
                self.assertEqual(
                    hashlib.sha256((ROOT / entry.get("baseline_path", entry["path"])).read_bytes()).hexdigest(),
                    entry["sha256"],
                )

    def test_compose_has_required_secret_substitutions(self):
        compose = json.loads((DEPLOY / "compose.production.snapshot.json").read_text())
        for service in compose["services"].values():
            for key, value in service.get("environment", {}).items():
                if any(word in key for word in ("PASSWORD", "SECRET", "TOKEN", "KEY")):
                    self.assertTrue(value.startswith("${"), key)
                    self.assertIn(":?", value, key)
        self.assertEqual(len(compose["services"]), 6)

    def test_upgrade_template_preserves_deployed_behavior(self):
        source = (ROOT / "sql/dj_setup_database.in").read_text()
        deployed = (DEPLOY / "domserver/dj_setup_database").read_text()
        substitutions = {
            "@domserver_bindir@": "/opt/domjudge/domserver/bin",
            "@domserver_etcdir@": "/opt/domjudge/domserver/etc",
            "@domserver_webappdir@": "/opt/domjudge/domserver/webapp",
            "@domserver_exampleprobdir@": "/opt/domjudge/domserver/example_problems",
            "@domserver_databasedumpdir@": "/opt/domjudge/domserver/db-dumps",
        }
        for key, value in substitutions.items():
            source = source.replace(key, value)
        normalize = lambda text: [
            line.strip() for line in text.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        self.assertEqual(normalize(source), normalize(deployed))

    def test_pascal_support_is_in_source_install(self):
        makefile = (ROOT / "judge/Makefile").read_text()
        for name in ("prepare.php", "run-testlib", "vendor/testlib.pas", "vendor/COPYING", "vendor/NOTICE.md"):
            self.assertIn("pascal/" + name, makefile)


@unittest.skipUnless(shutil.which("php"), "PHP CLI required")
class PascalPreparationTests(unittest.TestCase):
    def prepare(self, files):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, source in files.items():
                (root / name).write_text(source)
            result = subprocess.run(
                ["php", "-r", "require $argv[1]; echo preparePascalExecutable($argv[2], 'compare');",
                 str(ROOT / "judge/pascal/prepare.php"), directory],
                capture_output=True, text=True,
            )
            return result, {p.name: p.read_bytes() for p in root.iterdir()}

    def test_native_pascal_stays_native(self):
        result, _ = self.prepare({"check.pas": "begin halt(42); end."})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("-orun 'check.pas'", result.stdout)
        self.assertNotIn("checker.bin", result.stdout)

    def test_fallback_and_quoted_filename(self):
        result, files = self.prepare({"check ' quoted.dpr": "uses testlib; begin quit(_ok, 'ok'); end."})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("-ochecker.bin", result.stdout)
        self.assertIn(".domjudge-pascal-run", files)
        self.assertEqual(files["testlib.pas"], (ROOT / "judge/pascal/vendor/testlib.pas").read_bytes())
        self.assertIn("'\\''", result.stdout)

    def test_packaged_unit_is_not_overwritten(self):
        unit = "unit testlib; interface implementation end."
        result, files = self.prepare({"check.pp": "uses testlib; begin end.", "testlib.pas": unit})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(files["testlib.pas"], unit.encode())

    def test_ambiguous_programs_are_rejected(self):
        result, _ = self.prepare({"a.pas": "begin end.", "b.pp": "begin end."})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("exactly one program", result.stderr)


class PascalProtocolTests(unittest.TestCase):
    def test_mock_checker_exit_codes_and_private_output_cleanup(self):
        for checker_status, expected in ((0, 42), (1, 43), (2, 43), (4, 43), (3, 1), (7, 1), (139, 1)):
            with self.subTest(checker_status=checker_status), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                shutil.copyfile(ROOT / "judge/pascal/run-testlib", root / "run")
                checker = root / "checker.bin"
                checker.write_text("#!/bin/sh\necho synthetic-checker\nexit " + str(checker_status) + "\n")
                checker.chmod(0o700)
                (root / "feedback").mkdir()
                for name in ("input", "answer"):
                    (root / name).write_text("7\n")
                    (root / name).chmod(0o444)
                result = subprocess.run(
                    ["sh", str(root / "run"), str(root / "input"), str(root / "answer"), str(root / "feedback")],
                    input="7\n", capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, expected, result.stderr)
                self.assertEqual(list((root / "feedback").glob(".pascal-output.*")), [])
                self.assertEqual((root / "feedback/judgeerror.txt").exists(), expected == 1)


if __name__ == "__main__":
    unittest.main()
