"""Atlas shared domain library.

Imported by the engine, the API, the worker, and the backtester alike. See
``docs/MASTER_SPEC.md`` §4.4 for what belongs here and why duplication out of
this package is a defect rather than a style preference.

R-4.3.a: nothing in this package may import a vendor SDK.
R-4.4.a: feature and rule code lives here so training and live share one implementation.
"""

__all__ = ["__version__"]

__version__ = "0.0.0"
