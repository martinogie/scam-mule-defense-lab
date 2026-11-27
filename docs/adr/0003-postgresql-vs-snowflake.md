# ADR 0003: PostgreSQL versus Snowflake for cases, alerts and website marts

- **Status:** proposed (Phase 0, 19 Nov 2026). Accepted once the conclusion below is written.
- **Deciders:** Martins Ogiekpolor

## Context

Besides the heavy analytics (done on Databricks), the project needs one database for:

1. **Case management** (Phase 7): alerts, cases, analyst decisions, notes, timestamps and an
   **audit trail**: who did what, when.
2. **Decisions from the scoring service**: every scored payment's action, reasons and model
   version.
3. **Website marts**: small summary tables the website is built from, made with dbt.

Martins already runs Snowflake in the Bank Health project (paid Standard edition, with spending
caps), and PostgreSQL there as a local mirror for browsing. So both tools are familiar. The
question is which fits *this* project's job.

## What matters

1. **The workload.** Case management is many small writes and updates, done in transactions
   ("open case, assign analyst, record decision"). An audit trail must be complete and in order.
   That is classic transactional (OLTP) work.
2. **Cost:** free services only, or as close to free as possible.
3. **Runs on the PC and on the VM**, next to the scoring service, without depending on an outside
   service for the live demo.
4. **dbt support**, and easy browsing in pgAdmin or DBeaver.
5. **What it shows an interviewer.**

## Options considered

| Option | Strengths | Weaknesses |
|---|---|---|
| **PostgreSQL** | Built for transactions: row updates, constraints, foreign keys, triggers for an audit trail. Free; runs in Docker on the PC and the VM. dbt-postgres is mature. Easy to browse. Many banks run it. | Not built for very large analytics. Here the large analytics run on Databricks, and the marts are small. |
| **Snowflake** | A leading cloud data warehouse, widely used in banks. Separate storage and compute; excellent for large analytics. | Costs money for every query (credits). Built for analytics, not for many small transactional updates. The live demo would depend on an outside paid service. Already demonstrated in Bank Health, so it adds little here. |
| **DuckDB** | Free, very fast for analytics, a single file | Not a server: one writer at a time, no concurrent case API with an audit trail |
| **Databricks SQL** | Already used for training and features | The Free Edition's compute quota is shared with the heavy jobs; not suited to a transactional case API |

## Trade-offs

- Choosing PostgreSQL gives up Snowflake's scale and its name on this project. That's acceptable
  because the data here is small, Databricks does the heavy lifting, and Snowflake is already
  shown in Bank Health.
- PostgreSQL adds a service to the VM (1 GB cap, [ADR 0004](0004-oracle-vm-memory-budget.md)).

## Consequences

- `docker-compose.yaml` runs PostgreSQL 17 with small-machine settings (256 MB shared buffers, 40
  connections, 1 GB container cap).
- Separate databases per environment: `scam_mule` (prod), `scam_mule_dev`, `scam_mule_ci`.
- dbt models are written in portable SQL where reasonable, so a move to Snowflake stays possible.
- **At a real bank** the likely split is the same idea at a bigger size: a transactional database
  behind the case management tool, and a warehouse (Snowflake, Databricks or similar) for
  analytics and reporting. The model card and interview answers should say so.

## Conclusion

*To be written by Martins, in his own words.*
