# ADR-0001: Record architecture decisions

- **Date:** 2026-09-16
- **Status:** accepted
- **Rule deviated from:** none — new decision

## Context

`docs/MASTER_SPEC.md` states rules as MUST / SHOULD / MAY. Real projects deviate from their
specifications. The failure mode worth preventing is not deviation itself — it is deviation that
nobody recorded, so that a later reader cannot tell whether a difference between the spec and the code
is a deliberate choice or a bug. In a system where some rules exist to bound financial loss, that
ambiguity is expensive.

## Decision

Every deviation from a MUST or a SHOULD gets a numbered ADR in `docs/decisions/`, using
`0000-template.md`. ADRs are immutable once accepted; a change is a new ADR that supersedes the old
one. The specification's §0.5 points here.

## Consequences

Slightly more friction on every design change. In exchange, the spec and the code can be reconciled by
reading, and the reasoning behind an unusual choice survives the person who made it.

## Revisit when

Never. If ADRs become burdensome the answer is shorter ADRs, not fewer.
