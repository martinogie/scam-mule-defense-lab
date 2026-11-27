# Contributing

How a change gets from an idea to `main` without breaking anything. The short version: work on a
branch, run the checks locally, open a pull request, let CI pass, review, merge. The always-on
demo only ever runs `main`.

## Ground rules

- **This repository is public.** Never commit passwords, tokens, keys, `.env` files, IP
  addresses, hostnames or account URLs. Use placeholders and environment variables. The
  pre-commit hooks and the CI `secrets` job scan for leaks, but they are a safety net, not a
  licence to be careless.
- **No real personal data.** Every customer, account and payment is simulated. Sanctions lists
  are only matched against synthetic names. CFPB complaint stories appear only as totals or short
  paraphrases.
- **No evasion content.** Detection is described at the level of public guidance. Nothing here
  explains how to get around fraud or AML controls.
- **Honest framing.** Every result says whether it comes from the calibrated simulation, from
  real public data, or from the outside benchmark.

## Environments: dev, ci and prod

| | dev | ci | prod |
|---|---|---|---|
| Where | your PC | GitHub Actions | the Oracle VM (always-on demo, shared with Bank Health) |
| `SCAM_MULE_ENV` | `dev` | `ci` | `prod` |
| Compose | `docker-compose.yaml` + `docker-compose.dev.yaml` (project `scam-mule-dev`) | `docker-compose.yaml` (project `scam-mule-ci`, thrown away) | `docker-compose.yaml` (project `scam-mule`) |
| PostgreSQL database | `scam_mule_dev` | `scam_mule_ci` | `scam_mule` |
| Topic / key prefix | `dev.` / `dev:` | `ci.` / `ci:` | `prod.` / `prod:` |
| May write prod, publish, promote a model | no | no | yes |

There is no default environment: if `SCAM_MULE_ENV` is missing or misspelled, the code stops
instead of guessing (`common/environment.py`). Prod also refuses placeholder passwords.

## Set up (once)

```bash
uv sync                      # Python 3.12 + the dev tools, exactly as pinned in uv.lock
uv run pre-commit install    # run the checks on every commit (Docker must be running for gitleaks)
cp .env.example .env         # then choose your own passwords in .env
```

## Before every commit

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pytest --cov
```

The pre-commit hooks run most of this automatically when you commit.

## Run the local stack

```bash
docker compose up -d --wait   # with .env from .env.example, this is the dev stack
docker compose ps             # every service should say "(healthy)"
docker compose stop           # free the memory when you're done (keeps the data)
docker compose down -v        # remove everything, including the data
```

## Pull requests

1. Branch from `main` (for example `phase-1/cfpb-loader`).
2. Keep each pull request to one idea. Describe what changed, why, and how it was tested.
3. CI must be green: `lint`, `types`, `test`, `secrets`, `stack (linux/amd64)`,
   `stack (linux/arm64)`.
4. Every major design choice gets an ADR in `docs/adr/`.

## Standards

- Logic lives in importable, tested Python packages. Notebooks are thin wrappers.
- Test coverage of at least 80% for `scamsim/`, `features/`, `models/policy/`, `serving/` and
  `common/`.
- No peeking into the future: event-time features, as-of joins, leakage tests.
- Short "why" comments on choices that aren't obvious.
