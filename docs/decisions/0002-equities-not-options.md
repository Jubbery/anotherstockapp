# ADR-0002: Trade US equities, not options

- **Date:** 2026-09-16
- **Status:** accepted
- **Rule deviated from:** none — resolves open item O-3

## Context

The original brief described "top 50 day trade stock options" while also describing a scan over
"~8,000 US equities" and a stack built around equity bar data. These are two different systems with
different data, different risk models, and different failure modes. The ambiguity had to be resolved
before any schema or feature work, because it changes what the labelling scheme can even express.

## Decision

Atlas trades **US-listed common stock and ETFs** only. Options, futures, crypto, forex, and fixed
income are out of scope (spec §2.2, §2.3).

Reasoning:

- Options require a second pricing dimension (implied volatility surface), a Greeks-based risk model,
  and assignment/exercise handling. The risk governor — the component required to have 100% branch
  coverage and zero surviving mutants — would roughly triple in size.
- Option spreads are far wider in percentage terms. The Stage A liquidity filters that make the equity
  universe tradeable at this account size would eliminate most of the options universe.
- The triple-barrier labelling in §9.3 assumes a continuous, non-expiring underlying. Options need
  expiry as a hard barrier and contract rolling, which changes the label definition and the fill model.
- Alpaca's options support is a separate API surface with separate entitlements, forking §6 and §10.

## Consequences

The scope is narrower and the system is buildable by one person. Atlas cannot express a defined-risk
or leveraged view that options would allow, and cannot trade volatility directly.

If the operator later wants options exposure, that is a **new project** reusing Atlas's data layer and
control plane — not a feature added to this one.

## Revisit when

The equity system has been live and profitable for at least two quarters, and the operator has a
specific strategy that requires optionality rather than a general preference for it.
