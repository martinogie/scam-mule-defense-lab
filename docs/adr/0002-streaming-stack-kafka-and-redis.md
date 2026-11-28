# ADR 0002: Streaming stack: Apache Kafka for events, Redis for live features

- **Status:** proposed (27 Nov 2026). Accepted once the conclusion below is written.
- **Revision:** the first draft (19 Nov 2026) chose Redpanda for events. This version switches to
  Apache Kafka; see "Why we moved from Redpanda" below.
- **Deciders:** Martins Ogiekpolor

## Context

Instant payments can't be recalled, so the bank has to decide **before** the money moves. The
target is a decision in under 100 ms for 99 out of 100 payments (p99).

To decide that fast, two pieces are needed besides the scoring service itself:

1. **An event stream**, a conveyor belt that carries every payment, login and new payee as it
   happens, keeps them in order, and lets the simulator replay a day of events at any speed.
2. **A live feature store**, a very fast memory that holds facts about each customer, ready
   before the payment arrives: "first payment to this payee?", "third transfer in 10 minutes?".

Both must run on Martins' PC and in small configurations on the Oracle VM, which is shared with
the live Bank Health project ([ADR 0004](0004-oracle-vm-memory-budget.md)).

## What matters

1. **Speed:** feature lookups in about a millisecond, so the 100 ms budget is mostly left for the
   model and policy.
2. **Memory with a hard cap** on a shared VM.
3. **Recognised by banks:** the skills and the tool name should transfer directly to a bank job.
4. **Free:** free services only; no paid managed service.
5. **Simple to run** for one person: one container per piece, a health check, nothing exotic.
6. **Replay:** events kept long enough to replay a recorded day for the demo's stream panel.

## Why we moved from Redpanda

The first draft picked Redpanda because it is much lighter than Kafka, and at the time the VM's
spare memory was an estimate. Two things changed:

1. **The VM has more headroom than assumed.** Measured on 27 Nov 2026 at rest: 23 GB in total,
   about 2.6 GB used, about 20 GB available, with Bank Health's whole Airflow stack using about
   1.1 GB ([ADR 0004](0004-oracle-vm-memory-budget.md)). Kafka's extra weight now fits easily
   inside this project's existing caps.
2. **Kafka is the industry and job-market standard.** Banks run Apache Kafka (or a managed
   version of it), and job adverts ask for Kafka by name. Running the real thing is worth more
   in an interview than running something that speaks its protocol.

**No code changes.** Redpanda speaks Kafka's protocol, which is why it was considered in the
first place. Anything written against one works against the other. Nothing had been written
against the stream yet anyway (it is first used in Phase 6).

## Options considered: event stream

| Option | Strengths | Weaknesses |
|---|---|---|
| **Apache Kafka 4.x (KRaft mode)**, chosen | The industry standard, under the Apache 2.0 licence. Since version 4.0 Kafka manages itself (KRaft), with no separate ZooKeeper cluster to run. Official image with Intel and Arm builds. | Runs on the Java virtual machine: more memory than Redpanda, and every Kafka command-line tool starts its own Java process (a few seconds of a full CPU core each). Needs care with heap size and health checks. |
| **Redpanda**, the main alternative | Speaks the Kafka protocol, so the same client code works. A single C++ program, smaller, with exact memory and CPU caps. Arm images. | Not the name banks and job adverts use. The free Community Edition is source-available (BSL 1.1): free to use, but it may not be sold as a streaming service. Fine here, but less open than Kafka. |
| **Redis Streams** | One less component, since Redis is there anyway | Not the Kafka protocol, so less transferable. Weaker for long retention and replay. |
| **Managed cloud** (Confluent Cloud, Amazon MSK, Azure Event Hubs) | No servers to look after | Costs money; another account to secure; demo depends on a third party |
| **No stream** (call the scorer directly) | Simplest | Misses the point: no replay, no live feature updates, nothing like a real payments system |

## Options considered: live feature store

| Option | Strengths | Weaknesses |
|---|---|---|
| **Redis**, chosen | Lookups in well under a millisecond. Built-in expiry (TTL) and sorted sets suit "in the last 10 minutes" counts. Memory cap with automatic eviction. Widely used in fraud systems. | Data lives in memory, so it is lost on restart unless saved (here it is rebuilt from the stream instead). Redis 8 is offered under three licences (RSALv2, SSPLv1 or AGPLv3); using it unmodified for a portfolio is fine. |
| **Valkey** | A drop-in Redis fork under the BSD licence (Linux Foundation) | Less name recognition in job adverts; can be swapped in later if the licence ever matters |
| **PostgreSQL** | Already in the stack | Disk-based and slower under load; a risk for p99 under 100 ms |
| **Memory inside the scoring service** | Fastest possible | Lost on every restart; not shared if more than one copy of the service runs |
| **Feast** (feature store framework) on top of Redis | Standard definitions of features for batch and live | An extra layer to learn and run; our shared definitions in `features/` cover the same need more simply |

## Trade-offs

- Kafka over Redpanda trades a smaller footprint for the industry-standard tool. Measured on the
  PC at rest, the Kafka broker uses about **400 MB** inside its 1.5 GB cap.
- Kafka's health check is itself a small Java program, and each run costs a full CPU core for
  several seconds. Checking every 15 seconds averaged 38% of a core on the PC, so the check runs
  every 5 seconds while Kafka starts and once a minute after that (about 13% of a core). On the
  4-core VM, at half the normal CPU priority, that is a few percent of the machine.
- One broker that is also its own controller. A bank would run at least three of each so that
  losing a machine loses nothing. For a demo whose events are synthetic and can be replayed, one
  is enough.
- No password on Kafka (plain, unencrypted connections), like Redpanda before it. It listens on
  127.0.0.1 only, so only programs on the same machine can reach it. A bank would add TLS
  encryption and SASL logins.
- Redis is used as a **cache, not a database**: nothing is saved to disk, and live features can be
  rebuilt by replaying the stream. This keeps it small and simple.
- How events are processed (plain Python consumers, or a framework such as Flink or Bytewax) is
  decided in Phase 6, not here.

## Consequences

- `docker-compose.yaml` runs `apache/kafka:4.4.0` (one broker in KRaft mode, 1 CPU core, a fixed
  512 MB Java heap, 1.5 GB container cap, no swap) and Redis (256 MB of data, 512 MB container
  cap, least-recently-used keys dropped when full). The three data services together still fit
  the 3 GB slice in [ADR 0004](0004-oracle-vm-memory-budget.md).
- Kafka keeps a week of events (and at most 1 GB per partition) for replays.
- Topics are never created automatically: a mistyped topic name fails instead of quietly creating
  a new, empty topic. A test checks this setting.
- A test also checks that Kafka's heap is at most half its container cap, leaving room for Java's
  own overhead and the file cache Kafka relies on.
- Topic and key names carry the environment (`dev.payments`, `prod:customer:42`), so dev and prod
  never mix (`common/environment.py`). Topic names use dots only, never underscores.
- Neither service is ever reachable from outside the machine: ports open on 127.0.0.1 only, with a
  password on Redis.
- CI starts the stack on Intel and on Arm and proves Kafka works by sending a message and reading
  it back.
- Phase 6 must show a **live-versus-offline match test**: a feature computed from the stream equals
  the same feature computed in batch.

## Conclusion

*To be written by Martins, in his own words.*
