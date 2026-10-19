"""Exercise cleanup with fake DB/Docker; never contact production."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).with_name("domjudge-clean-judgehost-cache")


class CleanupTests(unittest.TestCase):
    def run_case(self, case):
        with tempfile.TemporaryDirectory() as root:
            cache = Path(root) / "judgedaemon-0-0/endpoint-default/testcase"
            old = cache / "old"
            fresh = cache / "fresh"
            old.mkdir(parents=True)
            fresh.mkdir()
            os.utime(old, (1, 1))
            executables = cache.parent / "executable/compare"
            old_executable = executables / "old"
            fresh_executable = executables / "fresh"
            old_executable.mkdir(parents=True)
            fresh_executable.mkdir()
            os.utime(old_executable, (1, 1))
            command = r'''
eval "$(sed '$d' "$SCRIPT")"
JUDGINGS_ROOT=$TEST_ROOT
db() {
    case "$1" in
        'SELECT enabled'*) [[ $CASE == disabled ]] && echo 0 || echo 1 ;;
        'SELECT COUNT(*) FROM judgehost WHERE enabled'*) [[ $CASE == last ]] && echo 0 || echo 3 ;;
        'SELECT COUNT(*) FROM judgetask'*)
            if [[ $CASE == busy ]]; then echo 2
            elif [[ $CASE == race && -e $TEST_ROOT/actions ]]; then echo 1
            else echo 0; fi ;;
        'UPDATE judgehost SET enabled=0'*) echo disable >> "$TEST_ROOT/actions" ;;
        'UPDATE judgehost SET enabled=1'*) echo enable >> "$TEST_ROOT/actions" ;;
        'SELECT COUNT(*) FROM judgehost WHERE hostname'*) echo 1 ;;
        *) return 1 ;;
    esac
}
docker() {
    echo "$1" >> "$TEST_ROOT/actions"
    [[ $CASE != stop_failure || $1 != stop ]]
}
sleep() { :; }
chown() { :; }
chmod() { :; }
[[ $CASE != dry ]] || DRY_RUN=1
[[ $CASE != full ]] || FULL=1
clean_host judgehost-0 60
'''
            result = subprocess.run(
                ["bash", "-c", command], text=True, capture_output=True,
                env={**os.environ, "SCRIPT": str(SCRIPT), "TEST_ROOT": root, "CASE": case},
            )
            self.assertEqual(result.returncode, 1 if case == "stop_failure" else 0, result.stderr)
            actions = (Path(root) / "actions")
            self.executable_cache = (old_executable.exists(), fresh_executable.exists())
            return old.exists(), fresh.exists(), actions.read_text() if actions.exists() else ""

    def test_old_only_rolling(self):
        self.assertEqual(self.run_case("normal"), (False, True, "disable\nstop\nstart\nenable\n"))

    def test_explicit_full(self):
        self.assertEqual(self.run_case("full")[:2], (False, False))
        self.assertEqual(self.executable_cache, (False, False))

    def test_expired_compiled_checkers_are_cleaned_only(self):
        self.run_case("normal")
        self.assertEqual(self.executable_cache, (False, True))

    def test_busy_preserves_compiled_checkers(self):
        self.run_case("busy")
        self.assertEqual(self.executable_cache, (True, True))

    def test_busy_skipped(self):
        self.assertEqual(self.run_case("busy"), (True, True, ""))

    def test_disabled_preserved(self):
        self.assertEqual(self.run_case("disabled"), (True, True, ""))

    def test_last_available_preserved(self):
        self.assertEqual(self.run_case("last"), (True, True, ""))

    def test_dry_run_read_only(self):
        self.assertEqual(self.run_case("dry"), (True, True, ""))

    def test_fetch_race_restores_host(self):
        self.assertEqual(self.run_case("race"), (True, True, "disable\nenable\n"))

    def test_stop_failure_restores_host_without_deleting(self):
        self.assertEqual(self.run_case("stop_failure"), (True, True, "disable\nstop\nstart\nenable\n"))


if __name__ == "__main__":
    unittest.main()
