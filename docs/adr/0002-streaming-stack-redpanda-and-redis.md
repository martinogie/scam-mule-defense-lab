# ADR 0002: Streaming stack: Redpanda for events, Redis for live features

- **Status:** proposed (Phase 0, 19 Nov 2026). Accepted once the conclusion below is written.
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
2. **Small memory footprint**, with a hard cap, on a shared 24 GB VM.
3. **Recognised by banks:** Kafka's interface is the industry standard for event streaming, so
   using it makes the skills transferable.
4. **Free:** free services only; no paid managed service.
5. **Simple to run** for one person: one container per piece, a health check, nothing exotic.
6. **Replay:** events kept long enough to replay a recorded day for the demo's fallback.

## Options considered: event stream

| Option | Strengths | Weaknesses |
|---|---|---|
| **Apache Kafka** (KRaft mode, no ZooKeeper) | The industry standard; Apache 2.0 licence | Runs on the Java virtual machine, which needs more memory and tuning; heavier to run in a small, capped container |
| **Redpanda** | Speaks the Kafka protocol, so the same client code and skills apply. A single program written in C++, with no Java or ZooKeeper. Memory and CPU can be capped exactly (`--memory`, `--smp`). Arm images for the VM. | Smaller community than Kafka. The free Community Edition uses a source-available licence (BSL 1.1): free to use, but you may not sell it as a streaming service. That's fine here. |
| **Redis Streams** | One less component, since Redis is there anyway | Not the Kafka protocol, so less transferable to bank interviews. Weaker for long retention and replay. |
| **Managed cloud** (Confluent Cloud, Amazon Kinesis, Azure Event Hubs) | No servers to look after | Costs money; another account to secure; demo depends on a third party |
| **No stream** (call the scorer directly) | Simplest | Misses the point: no replay, no live feature updates, nothing like a real payments system |

## Options considered: live feature store

| Option | Strengths | Weaknesses |
|---|---|---|
| **Redis** | Lookups in well under a millisecond. Built-in expiry (TTL) and sorted sets suit "in the last 10 minutes" counts. Memory cap with automatic eviction. Widely used in fraud systems. | Data lives in memory, so it is lost on restart unless saved (here it is rebuilt from the stream instead). Redis 8 is offered under three licences (RSALv2, SSPLv1 or AGPLv3); using it unmodified for a portfolio is fine. |
| **Valkey** | A drop-in Redis fork under the BSD licence (Linux Foundation) | Less name recognition in job adverts; can be swapped in later if the licence ever matters |
| **PostgreSQL** | Already in the stack | Disk-based and slower under load; a risk for p99 under 100 ms |
| **Memory inside the scoring service** | Fastest possible | Lost on every restart; not shared if more than one copy of the service runs |
| **Feast** (feature store framework) on top of Redis | Standard definitions of features for batch and live | An extra layer to learn and run; our shared definitions in `features/` cover the same need more simply |

## Trade-offs

- Redpanda over Kafka trades some community size for a much smaller, capped footprint. The code
  doesn't change if Kafka is used later, because both speak the same protocol.
- Redis is used as a **cache, not a database**: nothing is saved to disk, and live features can be
  rebuilt by replaying the stream. This keeps it small and simple.
- How events are processed (plain Python consumers, or a framework such as Flink or Bytewax) is
  decided in Phase 6, not here.

## Consequences

- `docker-compose.yaml` runs Redpanda (1 core, 1 GB for Redpanda itself, 1.5 GB container cap) and
  Redis (256 MB of data, 512 MB container cap, least-recently-used keys dropped when full).
- Topic and key names carry the environment (`dev.payments`, `prod:customer:42`), so dev and prod
  never mix (`common/environment.py`).
- Neither service is ever reachable from outside the machine: ports open on 127.0.0.1 only, with a
  password on Redis.
- Phase 6 must show a **live-versus-offline match test**: a feature computed from the stream equals
  the same feature computed in batch.

## Conclusion

*To be written by Martins, in his own words.*
