# ADR-0003: Long-only for v1

- **Date:** 2026-09-16
- **Status:** accepted
- **Rule deviated from:** §2.1, which permitted both directions. Resolves open item **O-5**.

## Context

§2.1 allowed long and short, subject to locate and shortability checks. The
operator was asked (O-5) whether to launch with both, and chose **long-only for
v1, to be safe**.

## Decision

Atlas v1 trades **long only**. Short selling is deferred, not deleted.

Concretely:

- Authorization grants may carry `sides_allowed = {long}` only. A grant
  requesting `short` is rejected by the API validator.
- The risk governor's short-specific rule (R-12.2.ac, shortable and
  easy-to-borrow) **remains implemented and tested**, and additionally rejects
  any short intent outright while `shorts_enabled` is false. It is not deleted
  and not commented out — a risk rule removed under one set of assumptions is a
  risk rule nobody re-derives correctly when the assumptions change.
- Stage A rule A7 (shortability) becomes inactive for candidate selection but
  stays in the predicate set, evaluated and recorded.
- Triple-barrier labelling (§9.3) generates `side = +1` only, so the model is
  trained on the population it will actually trade.
- Borrow cost stays in the cost model (§8.3.1) with a zero contribution, per
  R-8.3.a's rule against hardcoding a fee to zero.

## Consequences

**Simpler and safer.** No locate or borrow mechanics, no hard-to-borrow fee
surprises, no unbounded loss on a squeeze — a long position's worst case is
bounded at zero, a short's is not. For a first live system with an operator who
is also the author, that asymmetry is worth a great deal.

**Fewer opportunities, concentrated in one regime.** Atlas will find less to do
on broadly down days, and its results will correlate with the market more than a
long/short book would. The operator should expect the equity curve to look like
"long equities, but only sometimes" rather than something market-neutral. This
is a real cost and it is accepted deliberately.

**One risk rule becomes less exercised.** R-12.2.q (net exposure within ±60%) is
largely subsumed by R-12.2.p (gross exposure ≤ 100%) when every position is
long, since net equals gross. Both remain enforced; the net check earns its keep
again when shorts return.

**The ML layer sees a narrower problem.** Labels carry one side, so Stage B
ranks "which of these will go up" rather than "which will move, and which way".
That is a genuinely easier question and may improve the model's odds of clearing
the G1 baseline gate — or may simply make the baseline harder to beat, since
`stage_a_score` is also being asked an easier question.

## Revisit when

Atlas has traded live, long-only, profitably for at least one full quarter
**and** the operator wants exposure on down days badly enough to accept locate
mechanics and unbounded single-name downside. Re-enabling is a config flag plus
a review of R-12.2.ac and the label generator — deliberately small, because
nothing was deleted.
