"""Policy checks: no DB-history deletion and no raw Docker-log truncation."""
from pathlib import Path
import sqlite3
import subprocess
import unittest

DEPLOY = Path(__file__).resolve().parents[1]
ROOT = DEPLOY.parents[1]


class RetentionSafetyTests(unittest.TestCase):
    def test_destructive_retention_flag_is_rejected_before_docker(self):
        result = subprocess.run(
            ["bash", str(DEPLOY / "maintenance/domjudge-retention"), "--apply"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("deletion is disabled", result.stderr)

    def test_log_truncation_flag_is_rejected(self):
        result = subprocess.run(
            ["sh", str(DEPLOY / "maintenance/domjudge-clean-runtime-logs.sh"), "--apply"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 2)

    def test_retention_sql_is_read_only(self):
        source = (DEPLOY / "maintenance/domjudge-retention").read_text()
        sql = source.split("<<SQL\n", 1)[1].split("\nSQL", 1)[0]
        self.assertIn("SET TRANSACTION READ ONLY", sql)
        self.assertNotRegex(sql.upper(), r"\b(DELETE|UPDATE|TRUNCATE|DROP|ALTER)\b")
        self.assertIn("LIMIT $batch", sql)

    def test_log_script_never_truncates_or_vacuums(self):
        source = (DEPLOY / "maintenance/domjudge-clean-runtime-logs.sh").read_text()
        commands = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))
        self.assertNotIn("truncate ", commands)
        self.assertNotIn("--vacuum", commands)
        self.assertNotIn("/var/lib/docker/containers", commands)

    def test_all_maintenance_uses_one_lock(self):
        for path in ("maintenance/domjudge-clean-judgehost-cache", "maintenance/domjudge-retention",
                     "maintenance/domjudge_workdir_cleanup.py"):
            self.assertIn("/run/domjudge-maintenance.lock", (DEPLOY / path).read_text())

    def test_recovery_service_handles_forceful_termination(self):
        source = (DEPLOY / "systemd/domjudge-clean-judgehost-cache.service").read_text()
        self.assertIn("ExecStopPost=/usr/local/sbin/domjudge-clean-judgehost-cache --restore-only", source)

    def test_null_result_predicate_really_includes_unfinished_judging(self):
        source = (ROOT / "webapp/src/Controller/API/JudgehostController.php").read_text()
        self.assertIn("(j.result IS NULL OR j.result != :compiler_error)", source)
        with sqlite3.connect(":memory:") as connection:
            connection.execute("CREATE TABLE judging (id INTEGER, result TEXT)")
            connection.executemany("INSERT INTO judging VALUES (?,?)", [(1, None), (2, 'compiler-error'), (3, 'correct')])
            old = connection.execute("SELECT id FROM judging j WHERE j.result != ?", ('compiler-error',)).fetchall()
            new = connection.execute("SELECT id FROM judging j WHERE (j.result IS NULL OR j.result != ?)",
                                     ('compiler-error',)).fetchall()
        self.assertEqual(old, [(3,)])
        self.assertEqual(new, [(1,), (3,)])


if __name__ == "__main__":
    unittest.main()
