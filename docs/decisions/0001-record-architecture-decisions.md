# 1. Record architecture decisions

**Status:** Accepted · **Date:** 2026-09-16

## Context

`MASTER_SPEC.md` fixes a number of stack and design decisions. Some will turn out to be wrong. Without a
record of *why* each was made, a future session cannot tell a deliberate constraint from an accident, and
will either cargo-cult it or discard it for the wrong reason.

## Decision

Every deviation from `MASTER_SPEC.md` gets an ADR in this directory, numbered sequentially, with:
Context / Decision / Consequences, and an explicit note of which spec rule (`R-x.y.z`) it supersedes.

A rule marked **MUST** in the spec may only be superseded by an ADR that the operator has approved.

## Consequences

Slightly more ceremony per change. In exchange, the spec stays trustworthy — when it and the code disagree,
the ADR log says which is stale.

## Superseded spec rules

None.
