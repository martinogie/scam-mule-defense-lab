# ADR 0001: Simulated data, with scamsim as an agent-based model

- **Status:** proposed (Phase 0, 19 Nov 2026). Accepted once the conclusion below is written.
- **Deciders:** Martins Ogiekpolor

## Context

Every part of this project (the scam model, the decision policy, the warning experiment, mule
detection, AML prioritisation) needs payment data with true answers: which payments were scams,
which accounts were mules, and when the bank found out.

**No such data is public, and none can be.** Real bank transactions are protected by privacy law,
and disclosing a suspicious activity report (SAR) is a federal crime. Public fraud datasets exist,
but they are mostly card fraud, where a criminal uses stolen details. This project is about
**scams**, where the genuine customer is tricked into sending the money themselves. That is a
different problem with different signals.

So the data has to be made. The question is how to make it in a way an interviewer, a model risk
reviewer or a fraud lead would take seriously.

## What matters

1. **The problem must stay honestly hard.** Scam and genuine behaviour must overlap (a house
   deposit can look like a scam transfer). If the fake data is too easy, every model looks
   brilliant and every result is worthless.
2. **Realistic messiness:** scams are rare by count but a large share of dollars; losses have a
   long tail; labels arrive late, never, or wrong.
3. **Cause and effect.** The bank's decisions must change what happens next: a warned victim
   sometimes stops; a blocked scammer switches tactics. Without this, the warning A/B test and the
   adaptation work (Phases 4 and 8) can't be done at all.
4. **A known truth to check against.** Each warning's true effect must be a hidden setting, so we
   can show the A/B test recovers it and the naive comparison doesn't.
5. **Money networks.** Mule detection (Phase 5) needs realistic chains of accounts that receive
   and forward money.
6. **Repeatable:** the same seed gives exactly the same data, from 1 to 24 months.
7. **Anchored to reality:** totals must match real published statistics (FTC, FBI IC3, CFPB,
   FinCEN, Federal Reserve).

## Options considered

| Option | What it is | Strengths | Weaknesses |
|---|---|---|---|
| A. Public datasets only | Use existing labelled datasets (card fraud datasets, PaySim, IBM AMLworld) | Nothing to build; others can compare results | Mostly card fraud or mobile money, not US bank scams. No session signals (on a phone call, remote-access app). No feedback from bank decisions. No hidden true warning effect. |
| B. Row-by-row random generator | Draw each payment from statistical distributions (amount, time, rail), and mark some as scams | Quick to build; easy to calibrate totals | Payments have no history or story. No networks, no grooming over weeks, no reactions. Scams tend to be separable by construction, so the problem is too easy. |
| C. Generator trained on real data (for example a GAN) | Learn the patterns of a real dataset and produce look-alikes | Can be very realistic | Needs real labelled data to learn from, which is exactly what we don't have. |
| D. Agent-based model (scamsim) | Create small computer "people" (customers, small businesses, scammers, mules), give each traits and rules, and let them live day by day. The payments are the trail they leave. | Real stories (grooming, test payments, escalation). Networks arise naturally. Bank decisions feed back into behaviour. True effects can be hidden and later checked. Deterministic from a seed. | The biggest build in the project (Phase 2, 3-4 sessions). Risk of "the model finds what we built in." Slower to run at 210,000 agents over 24 months. |

**Prior art:** PaySim (Lopez-Rojas and others, 2016) simulated mobile-money fraud with agents.
IBM AMLworld (Altman and others, NeurIPS 2023) is itself a multi-agent simulation built for AML
research, and here it serves as the outside benchmark: data this project didn't make.

## Trade-offs and risks

- **"It's just fake data."** The strongest criticism, and it will come. The answers built into the
  design:
  - **Calibration targets as CI tests:** each target has a real source, a date, a value and a
    tolerance. If the simulator drifts outside a tolerance, CI fails and the change can't be
    merged.
  - **Stylised facts:** checks that scams are a bigger share of dollars than counts, that losses
    have a long tail, and that most mules are young accounts.
  - **A human "Turing test":** Martins reads 100 journeys (50 normal, 50 scam) and judges whether
    they are believable.
  - **The outside benchmark:** IBM AMLworld.
  - **Results as ranges** across seeds and assumption sets, never a single number.
- **"The model finds what we built in."** True of any simulation. The protections: deliberate
  overlap between scam and genuine behaviour, noisy and late labels, adaptive criminals, and
  sensitivity analysis showing which assumptions move the answer.
- **Effort and speed.** Phase 2 is the largest phase. Simulation code must be vectorised, and the
  24-month runs happen on Databricks, not on the PC or the VM.
- **Assumptions with no published figure** (for example the reporting delay) are written down as
  assumptions, with the range tested.

## Consequences

- `scamsim/` is the project's core asset and gets the strictest testing (coverage of at least 80%
  plus the calibration tests).
- `scamsim/calibration_targets.yaml` becomes the single list of real-world anchors, built in
  Phase 1 from the real public data.
- Every output must say which results come from the simulation, which from real public data, and
  which from the outside benchmark.
- In interviews, the honest answer to "is this real data?" is "no, and here is exactly how it is
  kept honest."

## Conclusion

*To be written by Martins, in his own words.*
