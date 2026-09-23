# cdjk Yakkha deterministic refresh

The Yakkha refresh is remote-only. Synchronize the current source tree to the
`cdjk` Ubuntu checkout without deleting remote SDK or evidence state, inspect
host headroom, and choose an absolute evidence path outside the checkout that
does not already exist.

```sh
cd /home/cdjk/github/llm/nepa-keyboard
bash tools/run_cdjk_yakkha_refresh.sh \
  /home/cdjk/data/nepa-keyboard/yakkha-refresh/20260716-v1
```

The runner owns the shared Nepa validation lock, rejects concurrent heavy work,
verifies the catalog/spec-pinned raw dictionary, builds independent adapter
trees and NKPs twice, compares normalized compiler reports, runs the milestone
finalizer in `--check` mode, and replays every checked-in Yakkha lookup vector.
It does not relock catalogs, invoke Gradle, or start an emulator.

Success requires the terminal line `yakkha_refresh_complete`, a
`refresh-summary.json` status of `ok`, zero values in `run-status.txt`, and a
`final-evidence-sha256.txt` manifest covering every retained input, build,
finalizer, vector, and host-preflight artifact. Never reuse or delete a failed
evidence directory; correct the source or environment and choose a new suffix.
