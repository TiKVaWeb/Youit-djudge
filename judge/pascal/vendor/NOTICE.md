# Pascal testlib

Source: `blackav/ejudge`, commit `c39d1f69a4b896954db93e8e18d8024ffb9f8c24`,
`checkers/delphi/testlib.pas`:
https://github.com/blackav/ejudge/blob/c39d1f69a4b896954db93e8e18d8024ffb9f8c24/checkers/delphi/testlib.pas

Upstream SHA-256: `37df53c0fd3d9af44fa61bac03e0f2dc73ffa26ea93453291a8521e7f17a588d`.
Copyright notices are preserved in the source. The upstream repository's GPLv2
license is included as `COPYING`; this vendored component is not relicensed.

Local adaptation: restore classic testlib exit codes (PE=2, WA=1 instead of
ejudge PE=4, WA=5) for the `run-testlib` protocol adapter, and open the input,
participant output and jury answer read-only (`FileMode = 0`) so unprivileged
validators can read protected test data. No checking logic was changed.
A task's explicitly supplied testlib unit takes precedence over this
fallback. The fallback implements the classic Pascal testlib API; other library
versions/dependencies should be packaged with their checker.
