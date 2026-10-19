#!/usr/bin/env python3
"""Bounded, fail-closed cleanup of completed judging scratch directories only."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import time

ROOT = Path("/mnt/domjudge-judgehost/judgings")
LOCK = "/run/domjudge-maintenance.lock"


class Database:
    def completed(self, submission, judging, cutoff):
        # IDs and cutoff are integers from validated directory names/configuration.
        sql = f"""SET SESSION max_statement_time=5;
SET TRANSACTION READ ONLY;
SELECT j.judgingid FROM judging j
WHERE j.judgingid={int(judging)} AND j.submitid={int(submission)}
  AND j.endtime IS NOT NULL AND j.endtime < {int(cutoff)}
  AND j.result IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM queuetask qt WHERE qt.judgingid=j.judgingid)
  AND NOT EXISTS (
    SELECT 1 FROM judgetask jt LEFT JOIN judging_run r ON r.judgetaskid=jt.judgetaskid
    WHERE jt.jobid=j.judgingid AND jt.valid=1
      AND (jt.type <> 'judging_run' OR r.endtime IS NULL));"""
        result = subprocess.run(
            ["docker", "exec", "-i", "mariadb", "sh", "-c",
             'MYSQL_PWD="$MYSQL_PASSWORD" exec mariadb -N -s -u "$MYSQL_USER" "$MYSQL_DATABASE"'],
            input=sql, text=True, capture_output=True, timeout=10, check=True,
        )
        rows = result.stdout.strip()
        if rows not in ("", str(int(judging))):
            raise RuntimeError("Unexpected database response; refusing cleanup")
        return bool(rows)


def positive(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def numeric(name):
    return name.isascii() and name.isdecimal() and int(name) > 0


def mounted_roots():
    mountinfo = Path("/proc/self/mountinfo")
    if not mountinfo.exists():
        return []  # macOS unit tests; production runs on Linux.
    result = []
    for line in mountinfo.read_text().splitlines():
        value = line.split()[4]
        for escaped, decoded in (("\\040", " "), ("\\011", "\t"), ("\\012", "\n"), ("\\134", "\\")):
            value = value.replace(escaped, decoded)
        result.append(Path(value))
    return result


def clean(root, database, cutoff, apply=False, max_candidates=1000, max_deletions=200):
    if not shutil.rmtree.avoids_symlink_attacks:
        raise RuntimeError("fd-safe rmtree required")
    if root.is_symlink() or root.resolve(strict=True) != root:
        raise RuntimeError("Judgings root must not traverse symlinks")
    report = {"candidates": 0, "eligible": 0, "deleted": 0, "skipped": 0, "apply": apply}
    # Never follow host/endpoint/submission symlinks; only the known daemon layout.
    for host in sorted(root.glob("judgedaemon-*-*")):
        parts = host.name.removeprefix("judgedaemon-").split("-")
        if len(parts) != 2 or parts[0] != parts[1] or not (parts[0].isascii() and parts[0].isdecimal()):
            continue
        if host.is_symlink() or not host.is_dir():
            continue
        endpoint = host / "endpoint-default"
        if endpoint.is_symlink() or not endpoint.is_dir():
            continue
        for submission in sorted(endpoint.iterdir()):
            if not numeric(submission.name) or submission.is_symlink() or not submission.is_dir():
                continue
            parent_fd = os.open(submission, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                for name in sorted(os.listdir(parent_fd)):
                    if not numeric(name):
                        continue
                    entry = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
                    if not stat.S_ISDIR(entry.st_mode) or entry.st_mtime >= cutoff:
                        continue
                    report["candidates"] += 1
                    target = submission / name
                    has_mount = any(mount == target or target in mount.parents for mount in mounted_roots())
                    if has_mount or not database.completed(int(submission.name), int(name), cutoff):
                        report["skipped"] += 1
                    else:
                        report["eligible"] += 1
                        if apply:
                            # Recheck identity after the DB roundtrip; never recurse through a replaced path.
                            current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
                            if (entry.st_dev, entry.st_ino) != (current.st_dev, current.st_ino):
                                raise RuntimeError("Workdir changed during cleanup")
                            shutil.rmtree(name, dir_fd=parent_fd)
                            report["deleted"] += 1
                    if report["candidates"] >= max_candidates or report["deleted"] >= max_deletions:
                        return report
            finally:
                os.close(parent_fd)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    parser.add_argument("--age-minutes", type=positive, default=360)
    parser.add_argument("--max-candidates", type=positive, default=1000)
    parser.add_argument("--max-deletions", type=positive, default=200)
    args = parser.parse_args()
    # Fixed production target: no environment-controlled recursive deletion root.
    with open(LOCK, "a", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('{"skipped":"another maintenance operation is running"}')
            return
        if Path("/run/domjudge-cache-cleanup.state").exists():
            print('{"skipped":"judgehost recovery is pending"}')
            return
        print(json.dumps(clean(
            ROOT, Database(), time.time() - args.age_minutes * 60,
            args.apply, args.max_candidates, args.max_deletions,
        )))


if __name__ == "__main__":
    main()
