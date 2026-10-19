"""All deletion targets are synthetic temporary directories, never production."""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "cleanup", Path(__file__).resolve().parents[1] / "maintenance/domjudge_workdir_cleanup.py"
)
cleanup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cleanup)


class FakeDatabase:
    def __init__(self, completed=()):
        self.allowed = set(completed)

    def completed(self, submission, judging, cutoff):
        return (submission, judging) in self.allowed


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.endpoint = self.root / "judgedaemon-0-0/endpoint-default"
        self.endpoint.mkdir(parents=True)

    def workdir(self, submission=10, judging=20, mtime=1):
        path = self.endpoint / str(submission) / str(judging)
        path.mkdir(parents=True)
        (path / "compile.success").write_text("synthetic")
        os.utime(path, (mtime, mtime))
        return path

    def test_only_confirmed_completed_judging_is_deleted(self):
        completed = self.workdir()
        active = self.workdir(judging=21)
        report = cleanup.clean(self.root, FakeDatabase([(10, 20)]), 100, apply=True)
        self.assertFalse(completed.exists())
        self.assertTrue(active.exists())
        self.assertEqual(report["deleted"], 1)

    def test_dry_run_is_default(self):
        path = self.workdir()
        report = cleanup.clean(self.root, FakeDatabase([(10, 20)]), 100)
        self.assertTrue(path.exists())
        self.assertEqual(report["eligible"], 1)
        self.assertEqual(report["deleted"], 0)

    def test_recent_workdir_is_preserved(self):
        path = self.workdir(mtime=200)
        cleanup.clean(self.root, FakeDatabase([(10, 20)]), 100, apply=True)
        self.assertTrue(path.exists())

    def test_nested_bind_mount_is_never_deleted(self):
        path = self.workdir()
        with patch.object(cleanup, "mounted_roots", return_value=[path / "compile/bind"]):
            cleanup.clean(self.root, FakeDatabase([(10, 20)]), 100, apply=True)
        self.assertTrue(path.exists())

    def test_unknown_judging_is_preserved(self):
        path = self.workdir()
        cleanup.clean(self.root, FakeDatabase(), 100, apply=True)
        self.assertTrue(path.exists())

    def test_unknown_host_layout_is_preserved(self):
        path = self.root / "judgedaemon-other-other/endpoint-default/10/20"
        path.mkdir(parents=True)
        os.utime(path, (1, 1))
        cleanup.clean(self.root, FakeDatabase([(10, 20)]), 100, apply=True)
        self.assertTrue(path.exists())

    def test_database_failure_is_fail_closed(self):
        path = self.workdir()
        database = FakeDatabase()
        database.completed = lambda *args: (_ for _ in ()).throw(RuntimeError("offline"))
        with self.assertRaises(RuntimeError):
            cleanup.clean(self.root, database, 100, apply=True)
        self.assertTrue(path.exists())

    def test_judging_symlink_is_never_followed(self):
        target = self.root / "do-not-delete"
        target.mkdir()
        submission = self.endpoint / "10"
        submission.mkdir()
        (submission / "20").symlink_to(target, target_is_directory=True)
        cleanup.clean(self.root, FakeDatabase([(10, 20)]), 100, apply=True)
        self.assertTrue(target.exists())
        self.assertTrue((submission / "20").is_symlink())

    def test_submission_symlink_is_never_followed(self):
        target = self.root / "outside"
        (target / "20").mkdir(parents=True)
        (self.endpoint / "10").symlink_to(target, target_is_directory=True)
        cleanup.clean(self.root, FakeDatabase([(10, 20)]), 100, apply=True)
        self.assertTrue((target / "20").exists())

    def test_root_symlink_is_rejected(self):
        alias = self.root / "alias"
        alias.symlink_to(self.endpoint, target_is_directory=True)
        with self.assertRaises(RuntimeError):
            cleanup.clean(alias, FakeDatabase(), 100, apply=True)

    def test_changed_inode_is_not_deleted(self):
        path = self.workdir()
        database = FakeDatabase()

        def replace(*args):
            path.rename(path.with_name("preserved"))
            path.mkdir()
            return True

        database.completed = replace
        with self.assertRaises(RuntimeError):
            cleanup.clean(self.root, database, 100, apply=True)
        self.assertTrue(path.exists())
        self.assertTrue(path.with_name("preserved").exists())

    def test_deletion_budget(self):
        self.workdir(judging=20)
        self.workdir(judging=21)
        report = cleanup.clean(self.root, FakeDatabase([(10, 20), (10, 21)]), 100,
                               apply=True, max_deletions=1)
        self.assertEqual(report["deleted"], 1)
        self.assertTrue((self.endpoint / "10/21").exists())

    def test_candidate_budget(self):
        self.workdir(judging=20)
        self.workdir(judging=21)
        report = cleanup.clean(self.root, FakeDatabase(), 100, apply=True, max_candidates=1)
        self.assertEqual(report["candidates"], 1)

    def test_database_confirmation_is_read_only_and_bounded(self):
        with patch.object(cleanup.subprocess, "run") as run:
            run.return_value = subprocess.CompletedProcess([], 0, "20\n", "")
            self.assertTrue(cleanup.Database().completed(10, 20, 100))
            sql = run.call_args.kwargs["input"]
            self.assertIn("SET TRANSACTION READ ONLY", sql)
            self.assertIn("j.submitid=10", sql)
            self.assertIn("j.endtime IS NOT NULL", sql)
            self.assertIn("jt.valid=1", sql)
            self.assertIn("jt.type <> 'judging_run' OR r.endtime IS NULL", sql)
            self.assertEqual(run.call_args.kwargs["timeout"], 10)

    def test_unexpected_database_response_is_rejected(self):
        with patch.object(cleanup.subprocess, "run") as run:
            run.return_value = subprocess.CompletedProcess([], 0, "21\n", "")
            with self.assertRaises(RuntimeError):
                cleanup.Database().completed(10, 20, 100)


if __name__ == "__main__":
    unittest.main()
