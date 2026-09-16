"""Money, prices, and share counts.

R-3.6.a / R-5.5.a: monetary quantities are ``Decimal``, never ``float``, and
``Money`` and ``Price`` are distinct types. The distinction is not pedantry --
``entry_price + realised_pnl`` is meaningless, and the type checker is a cheaper
place to discover that than a position-sizing calculation.

Statistical code may use floats on *returns and features*; the boundary is here.

Note on the arithmetic dunders: they carry precise annotations so that
``Money + Price`` is a static error, and they also check at runtime via
``_require_type``, because annotations are not enforced at import time and a
mixed-type addition reaching production would be silent. ``__eq__`` is the one
exception -- it takes ``object`` and returns ``NotImplemented``, since
``Money('10') != Price('10')`` must be ``True`` rather than an exception.
"""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Context, Decimal, InvalidOperation
from typing import Final

__all__ = ["MONEY_CONTEXT", "Money", "Price", "Quantity"]

# R-5.5.b. 28 significant digits is Python's default precision; the rounding mode
# is not guaranteed to stay so. Stating both means a `getcontext()` change
# elsewhere in the process cannot silently alter settlement arithmetic.
MONEY_CONTEXT: Final = Context(prec=28, rounding=ROUND_HALF_EVEN)

CENTS: Final = Decimal("0.01")

# Accepted inputs. `float` is deliberately absent: see _coerce.
type DecimalLike = Decimal | int | str


def _coerce(value: DecimalLike, *, field: str) -> Decimal:
    """Convert to ``Decimal``, rejecting floats loudly.

    ``Decimal(0.1)`` is ``0.1000000000000000055511151231257827021181583404541015625``.
    Accepting floats here would make that the cost basis of a position, so a float
    is a ``TypeError`` rather than something we round away.
    """
    if isinstance(value, float):
        raise TypeError(
            f"{field} must not be constructed from a float ({value!r}). "
            "Pass a str, int, or Decimal -- see MASTER_SPEC R-3.6.a."
        )
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"{field} could not be parsed as a decimal: {value!r}") from exc


def _require_type(value: object, expected: type, operation: str) -> None:
    """Enforce at runtime what the annotations say statically.

    Raises rather than returning ``NotImplemented`` so the message names the
    actual mistake. There are no subclasses here for the reflected-operand
    protocol to serve.
    """
    if not isinstance(value, expected):
        raise TypeError(
            f"{operation} requires {expected.__name__}, got {type(value).__name__}. "
            "Money, Price, and Quantity are distinct types -- see MASTER_SPEC R-5.5.a."
        )


class Quantity:
    """A whole number of shares.

    R-10.4.d: no fractional shares. They complicate shorting and stop placement
    for no benefit at this account size, so the type forbids them outright.
    """

    __slots__ = ("_shares",)

    def __init__(self, shares: int) -> None:
        # bool is an int in Python, and Quantity(True) is a bug rather than one share.
        if isinstance(shares, bool) or not isinstance(shares, int):
            raise TypeError(f"Quantity must be a whole number of shares, got {shares!r}")
        if shares < 0:
            raise ValueError(f"Quantity must not be negative, got {shares}. Side is separate.")
        object.__setattr__(self, "_shares", shares)

    @property
    def shares(self) -> int:
        value: int = object.__getattribute__(self, "_shares")
        return value

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("Quantity is immutable")

    def __repr__(self) -> str:
        return f"Quantity({self.shares})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Quantity):
            return NotImplemented
        return self.shares == other.shares

    def __hash__(self) -> int:
        return hash(("Quantity", self.shares))

    def __bool__(self) -> bool:
        return self.shares > 0


class Price:
    """A price per share.

    Prices keep full precision through intermediate arithmetic and are quantized
    to the symbol's tick size at order construction, not before (R-5.5.b).
    """

    __slots__ = ("_amount",)

    def __init__(self, amount: DecimalLike) -> None:
        object.__setattr__(self, "_amount", _coerce(amount, field="Price"))

    @property
    def amount(self) -> Decimal:
        value: Decimal = object.__getattribute__(self, "_amount")
        return value

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("Price is immutable")

    def __repr__(self) -> str:
        return f"Price('{self.amount}')"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Price):
            return NotImplemented
        return self.amount == other.amount

    def __hash__(self) -> int:
        return hash(("Price", self.amount))

    def __lt__(self, other: Price) -> bool:
        _require_type(other, Price, "Price <")
        return self.amount < other.amount

    def __le__(self, other: Price) -> bool:
        _require_type(other, Price, "Price <=")
        return self.amount <= other.amount

    def __gt__(self, other: Price) -> bool:
        _require_type(other, Price, "Price >")
        return self.amount > other.amount

    def __ge__(self, other: Price) -> bool:
        _require_type(other, Price, "Price >=")
        return self.amount >= other.amount

    def __mul__(self, quantity: Quantity) -> Money:
        """``Price x Quantity -> Money`` (R-5.5.a)."""
        _require_type(quantity, Quantity, "Price *")
        return Money(MONEY_CONTEXT.multiply(self.amount, Decimal(quantity.shares)))

    def __add__(self, other: Price) -> Price:
        _require_type(other, Price, "Price +")
        return Price(MONEY_CONTEXT.add(self.amount, other.amount))

    def __sub__(self, other: Price) -> Price:
        """Price difference -- e.g. risk per share, entry to stop (§12.3)."""
        _require_type(other, Price, "Price -")
        return Price(MONEY_CONTEXT.subtract(self.amount, other.amount))

    def abs(self) -> Price:
        return Price(abs(self.amount))

    def quantize_to_tick(self, tick: Decimal) -> Price:
        """Round to the symbol's tick size (R-10.4.d).

        Called once, at order construction. The direction of rounding is
        arbitrary here because the limit price's protective offset is applied
        first, so half a tick cannot carry a price across the collar in R-12.2.y.
        """
        if tick <= 0:
            raise ValueError(f"Tick size must be positive, got {tick}")
        return Price(self.amount.quantize(tick, rounding=ROUND_HALF_EVEN))


class Money:
    """An amount of currency. USD -- Atlas trades one market (§2.1)."""

    __slots__ = ("_amount",)

    def __init__(self, amount: DecimalLike) -> None:
        object.__setattr__(self, "_amount", _coerce(amount, field="Money"))

    @classmethod
    def zero(cls) -> Money:
        return cls(0)

    @property
    def amount(self) -> Decimal:
        value: Decimal = object.__getattribute__(self, "_amount")
        return value

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("Money is immutable")

    def __repr__(self) -> str:
        return f"Money('{self.amount}')"

    def __str__(self) -> str:
        """Exact, to cents (R-13.5.b)."""
        return f"{self.amount.quantize(CENTS, rounding=ROUND_HALF_EVEN)}"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        return self.amount == other.amount

    def __hash__(self) -> int:
        return hash(("Money", self.amount))

    def __lt__(self, other: Money) -> bool:
        _require_type(other, Money, "Money <")
        return self.amount < other.amount

    def __le__(self, other: Money) -> bool:
        _require_type(other, Money, "Money <=")
        return self.amount <= other.amount

    def __gt__(self, other: Money) -> bool:
        _require_type(other, Money, "Money >")
        return self.amount > other.amount

    def __ge__(self, other: Money) -> bool:
        _require_type(other, Money, "Money >=")
        return self.amount >= other.amount

    def __add__(self, other: Money) -> Money:
        _require_type(other, Money, "Money +")
        return Money(MONEY_CONTEXT.add(self.amount, other.amount))

    def __sub__(self, other: Money) -> Money:
        _require_type(other, Money, "Money -")
        return Money(MONEY_CONTEXT.subtract(self.amount, other.amount))

    def __neg__(self) -> Money:
        return Money(-self.amount)

    def __bool__(self) -> bool:
        return self.amount != 0

    def is_negative(self) -> bool:
        return self.amount < 0

    def to_json(self) -> str:
        """Serialise for the API as a string decimal (R-14.1.b).

        JSON numbers become IEEE-754 doubles in the browser, which is the same
        failure R-3.6.a prevents in Python. The boundary is defended on both sides.
        """
        return str(self.amount)
