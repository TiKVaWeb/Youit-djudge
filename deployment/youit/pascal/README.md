# Pascal executable support for DOMjudge

Adds automatic `.dpr`, `.pas`, `.pp` builds, including classic Pascal testlib
output checkers. No student code, test data or checker algorithm is rewritten.
Existing explicit `build`/`run` files and C/C++/Java/Python handling are unchanged.

## Components

- `Dockerfile` extends the pinned production judgehost image and installs Free
  Pascal **inside the existing chroot**. Compilation still runs through DOMjudge's
  `build_executable.sh` and `runguard` with existing memory/time/file limits.
- `prepare.php` selects exactly one main program, excluding Pascal units; ambiguous
  packages require their own build script. Source filenames are shell-quoted.
- Pascal `compare` programs using `testlib` get a fallback unit if none is packaged
  and a protocol adapter. Other Pascal executables compile directly to `run`.
- `run-testlib` passes input, a temporary copy of contestant stdout, and jury answer
  in testlib order. OK maps to 42; WA/PE/extra output to 43. Checker failure, crash,
  or unsupported exit status remains an internal error, **never accepted or WA**.
  Diagnostics go to DOMjudge feedback files; the temporary output is removed.
- `pascal-executables.patch` hooks this into the currently deployed daemon. It is
  based on SHA-256 `c1d1ca6d9ebad30237350a72d5eedacf9072ebb8cf1e10870f67080b7c320636`
  and preserves existing local cleanup fixes. Rebase the patch on DOMjudge upgrades.

## Test

```sh
docker build -t youit-judgehost:pascal-20260929 deploy/domjudge/pascal
docker run --rm --network none --user 65534:65534 --security-opt no-new-privileges \
  --entrypoint php -v "$PWD/deploy/domjudge/pascal:/support:ro" \
  youit-judgehost:pascal-20260929 /support/test.php
```

The tests exercise all source extensions, quoted filenames, extra units, ambiguous
entrypoints, correct/wrong/empty/trailing output, internal checker errors, temporary
file cleanup, read-only input/answer files as an unprivileged user, and native
DOMjudge Pascal executables. Also validate a real checker
against correct and wrong jury/participant answers before unblocking an incident.

## Rollout

1. Preserve the current Compose config, daemon override, image digest, and affected
   internal-error/contest-problem records. Build and test the image above.
2. Verify the deployed daemon's base hash, apply the patch in a temporary directory,
   and run `php -l`. Keep its existing read-only mount and other overrides.
3. Change only the four judgehost image references to the tested image and update
   the daemon override. Gracefully drain/recreate judgehosts sequentially; do not
   restart MariaDB, domserver, or student-facing backend services.
4. Check FPC inside each chroot and all judgehost poll times. Only then resolve the
   **specific verified** Pascal checker incident via DOMjudge's own service so its
   queued judgings are recreated normally. Never set verdicts manually.
5. Verify actual tests and final verdicts for every affected pending submission.

Rollback uses the saved Compose config and daemon override and recreates only the
judgehosts. Pause affected Pascal checkers before rollback; keep all original
submissions, tests, checker sources and completed verdicts.

This adds classic Pascal testlib output validators, not arbitrary interactive or
partial-scoring protocols. Task-supplied units must follow the classic testlib
exit-code contract; custom protocols should supply an explicit build/run adapter.
