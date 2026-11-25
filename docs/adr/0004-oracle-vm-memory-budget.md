# ADR 0004: Oracle VM memory budget, alongside Bank Health

- **Status:** proposed (Phase 0, 19 Nov 2026). Accepted once the measured Bank Health figures are
  filled in and the conclusion below is written.
- **Deciders:** Martins Ogiekpolor

## Context

The always-on demo (the scoring service, the "try a payment" endpoint and the data services
behind them) will run on Martins' Oracle Cloud VM: an Arm machine (Ampere A1) with **4 cores, 24 GB
of memory and a 4 GB swap file**.

That VM already runs **Bank Health in production**:

- Bank Health's Airflow stack uses about **3-4 GB** (its own estimate, in its
  `airflow/docker-compose.yaml`), plus its own PostgreSQL metadata database.
- Its weekly run starts **every Monday at 06:00 Chicago time**. Its promise (service level
  objective) is that the week's data is ready by **Monday 12:00**. The VM is busy for about 30
  minutes a week.
- **Bank Health comes first:** this project must never disturb Bank Health's Monday run.

The risk isn't average use; it's a **peak at the wrong moment**. If this project's containers
and Bank Health's Monday run together exceed memory, Linux's "out-of-memory killer" stops a
process, and it might pick Bank Health's. Heavy swapping would slow everything down instead.

## What matters

1. Bank Health's Monday run is never slowed or stopped by this project.
2. This project's memory use has a **hard ceiling**, enforced by Docker, not just intended.
3. If memory does run short anyway, **this project's containers die first**.
4. The demo still works the rest of the week, within its 100 ms p99 target.
5. Simple enough for one person to check in a minute.

## Proposed budget (to confirm with measured figures)

| Slice | Proposed | Measured (Martins fills in) |
|---|---|---|
| Operating system, Docker, SSH | 2 GB | ___ GB (`free -h` with all stacks stopped) |
| Bank Health, normal week | 3-4 GB (its estimate) | ___ GB (`docker stats --no-stream`, idle) |
| Bank Health, Monday-run peak, with room to grow | reserve **8 GB** | ___ GB (`docker stats` during the run) |
| Unallocated safety margin | at least **6 GB** | |
| **Scam & Mule Defense Lab, hard ceiling** | **6 GB** in total | |
| of which: Redpanda + Redis + PostgreSQL (Phase 0) | 3 GB (1.5 + 0.5 + 1) | `docker stats` |
| of which: scoring service (Phase 6) | 1 GB | |
| of which: stream processor (Phase 6) | 0.5 GB | |
| of which: public demo endpoint (Phase 10) | 0.5 GB | |
| of which: spare | 1 GB | |

2 + 8 + 6 + 6 = 22 GB, leaving 2 GB more on top of the margin. CPU: this project's caps add up to
at most 2.5 of the 4 cores for the Phase 0 services, at half the normal CPU priority.

## Options considered: where the batch work runs

| Option | Strengths | Weaknesses |
|---|---|---|
| **A. No scam-mule Airflow on the VM.** Batch work (simulation, training, downloads) runs on the PC and on Databricks; the VM only serves the demo. | Smallest footprint on the VM; no scheduled jobs that could collide with Monday | Batch runs need the PC or Databricks; the demo serves a fixed, replayed day |
| B. A second Airflow on the VM, for this project | Fully automated pipeline on the VM | Another 3-4 GB; two schedulers on one machine; more collision risk |
| C. Share Bank Health's Airflow | No extra memory | Ties the two projects together: a scam-mule bug or deploy could break Bank Health, which must always come first. |

The draft leans towards **A** for the always-on demo, with the heavy 24-month simulation and graph
training on Databricks, where the project plan already puts them.

## Protections for the Monday run

1. **Hard caps in Docker** (`mem_limit`, with `memswap_limit` equal to it, so no swap use) on every
   container, checked by a test (`common/tests/test_compose_files.py`) so a cap can't silently
   disappear.
2. **Die first:** `oom_score_adj: 500` on every container, so the kernel stops these before Bank
   Health's.
3. **Lower CPU priority:** `cpu_shares: 512` (Docker's normal is 1024), so Bank Health wins when
   both are busy.
4. **A no-go window, Sunday 22:00 to Monday 14:00 Chicago time** (proposed): no scheduled
   scam-mule jobs, no deploys, no image builds and no heavy replays on the VM. That's the 06:00
   start with 8 hours of margin before it, and 2 hours after the 12:00 promise. If Bank Health
   runs late or is re-run, scam-mule work waits until its run log shows success.
5. **Images built elsewhere** (in CI) and pulled, not built on the VM. Bank Health's runbook notes
   that image builds cause memory peaks.
6. **A one-line stop switch:** `docker compose -p scam-mule stop` frees all of this project's
   memory at once; it goes in the runbook.
7. **Watch it:** a memory alarm (for example, VM memory above 80%) is added with the monitoring
   work in Phase 8.

## Consequences

- `docker-compose.yaml` (prod) carries the Phase 0 caps today; later phases must fit inside the
  6 GB ceiling or come back to this ADR.
- The live demo replays a fixed recorded day instead of running the full simulator on the VM.
- Before the first deploy to the VM (Phase 6 or 10), Martins measures the real Bank Health figures
  and fills in the table above.
- The no-go window will be enforced in code by whichever component schedules work on the VM, with
  a test.

## Conclusion

*To be written by Martins, in his own words.*
