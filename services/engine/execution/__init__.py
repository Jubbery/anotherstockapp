"""Order construction, the single submission path, idempotency, reconciliation. Phase 5.

R-10.1.a: exactly one module here -- ``submit.py`` -- may call the broker's order
API, and everything reaches it through the risk governor. There is no bypass
parameter. A CI check greps the repository's AST for broker order calls outside
this path and fails if any exist (R-10.1.c).
"""
