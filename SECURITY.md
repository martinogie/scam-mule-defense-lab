# Security policy

## Reporting a problem

If you find a security problem (for example a leaked credential, an exposed service, or a way to
misuse the public demo), please report it **privately**:

- Use GitHub's **"Report a vulnerability"** button on the **Security** tab of this repository.
- Please don't open a public issue for security problems.

You can expect an acknowledgement within a week. This is a one-person portfolio project, so
there is no bug bounty.

## What this project holds

- **No real personal or banking data.** Every customer, account and payment is simulated, with
  generated names. Real public datasets (CFPB, FTC, FBI IC3, FinCEN, Federal Reserve, OFAC,
  OpenSanctions) are used only as published, and sanctions lists are only matched against
  synthetic names.
- **No secrets in the repository.** Passwords and keys live in git-ignored `.env` files on each
  machine. CI scans every commit for leaked secrets.

## The public demo

Only the demo endpoint is meant to be reachable from the internet. The internal services
(Kafka, Redis, PostgreSQL) listen on localhost only. If you can reach any of them from
outside, please report it as above.

## Responsible use

This project describes fraud and anti-money-laundering detection at the level of public
guidance. It does not, and will not, explain how to get around these controls.
