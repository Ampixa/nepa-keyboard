# Host-safety and remote-execution policy

The local Mac is an orchestration workstation, not a compute node. It has 18 GB
of RAM. A previous incident combined three large Python resident sets, extensive
swap pressure, an MPS alignment workload, other local training, a WindowServer
timeout, missed watchdog check-ins, and a kernel panic.

## Default host assignment

| Work | Host |
|---|---|
| Editing, `rg`, small `jq`/metadata checks, Git, SSH orchestration | Local Mac |
| Android SDK/NDK builds, Gradle, lint, unit/instrumentation tests | `cdjk` Ubuntu |
| Android emulator, screenshots, UI automation, performance tests | `cdjk` Ubuntu |
| Dictionary compilation over full corpora, OCR, alignment, bulk conversion | `cdjk` Ubuntu |
| Model training, evaluation, bulk inference | `cdjk` Ubuntu or a more suitable approved compute host |

`cdjk` is the default for this project. `k2`, `omac`, or another suitable remote
host may be selected when explicitly appropriate, but compute must not silently
fall back to the Mac.

## Before starting a remote workload

Run a lightweight preflight on the selected machine:

```sh
ssh cdjk 'hostname; uptime; free -h; df -h / /tmp; ps -eo pid,comm,%cpu,%mem,rss --sort=-rss | head -20'
```

If the job needs a GPU, also check the relevant accelerator status. Confirm that
there is enough free memory and disk for the peak workload and that another
large job is not already running. Prefer explicit concurrency and memory limits.

## Android workflow

All Android commands run remotely, including dependency resolution, compilation,
Gradle tests, lint, emulator startup, ADB-driven tests, screenshots, and
benchmarks. Source edits can remain local, but synchronize or use the remote
working tree before executing Android commands. Store test outputs and build
reports in a reproducible project path and copy back only the small artifacts
needed for review.

## Local checks

Lightweight local inspection is allowed. If host pressure is in doubt, inspect
it before continuing:

```sh
vm_stat
ps -axo pid,comm,%cpu,%mem,rss | sort -k5 -nr | head -20
```

Do not start a local workload merely because the remote host is unavailable.
Report the remote blocker or choose another approved remote machine.
