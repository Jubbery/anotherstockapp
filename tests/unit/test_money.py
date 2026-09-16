"""R-3.6.a / R-5.5.a: money is Decimal, and Money is not Price."""

from __future__ import annotations

from decimal import Decimal

import pytest

from atlas_core.domain.money import Money, Price, Quantity


@pytest.mark.parametrize("cls", [Money, Price])
def test_float_is_rejected(cls: type) -> None:
    """The whole point of the type. Decimal(0.1) is not 0.1."""
    with pytest.raises(TypeError, match="must not be constructed from a float"):
        cls(0.1)


@pytest.mark.parametrize("cls", [Money, Price])
def test_string_construction_is_exact(cls: type) -> None:
    assert cls("0.1").amount == Decimal("0.1")
    assert cls("0.1").amount + cls("0.2").amount == Decimal("0.3")


def test_price_times_quantity_is_money() -> None:
    result = Price("210.18") * Quantity(84)
    assert isinstance(result, Money)
    assert result.amount == Decimal("17655.12")  # not 17655.119999999998


def test_money_plus_price_is_a_type_error() -> None:
    """Adding a per-share price to a total is meaningless; the type says so."""
    with pytest.raises(TypeError):
        _ = Money("100") + Price("5")  # type: ignore[operator]


def test_price_plus_money_is_a_type_error() -> None:
    with pytest.raises(TypeError):
        _ = Price("5") + Money("100")  # type: ignore[operator]


def test_price_difference_is_risk_per_share() -> None:
    """§12.3 sizing: |entry - stop| is a price delta, not an amount of money."""
    risk = (Price("210.18") - Price("207.87")).abs()
    assert isinstance(risk, Price)
    assert risk.amount == Decimal("2.31")


def test_quantity_rejects_fractional_shares() -> None:
    """R-10.4.d."""
    with pytest.raises(TypeError):
        Quantity(1.5)  # type: ignore[arg-type]


def test_quantity_rejects_bool() -> None:
    """bool is an int in Python; Quantity(True) is a bug, not one share."""
    with pytest.raises(TypeError):
        Quantity(True)


def test_quantity_rejects_negative() -> None:
    """Side is carried separately; a negative share count is ambiguity."""
    with pytest.raises(ValueError, match="must not be negative"):
        Quantity(-1)


def test_values_are_immutable() -> None:
    price = Price("10.00")
    with pytest.raises(AttributeError):
        price.amount = Decimal("11.00")  # type: ignore[misc]


def test_money_renders_to_cents() -> None:
    """R-13.5.b: notifications state exact amounts."""
    assert str(Money("291.4567")) == "291.46"
    assert str(Money("-243")) == "-243.00"


def test_money_serialises_as_string_for_the_api() -> None:
    """R-14.1.b: JSON numbers become doubles in the browser."""
    assert Money("17654.12").to_json() == "17654.12"
    assert isinstance(Money("17654.12").to_json(), str)


def test_tick_quantization() -> None:
    """R-10.4.d: prices are quantized at order construction, not before."""
    assert Price("210.184").quantize_to_tick(Decimal("0.01")).amount == Decimal("210.18")
    # Half-even, not half-up: the dropped digit is an exact 5 and the kept digit
    # is already even, so 0.98765 stays at 0.9876. Sub-dollar ticks are $0.0001.
    assert Price("0.98765").quantize_to_tick(Decimal("0.0001")).amount == Decimal("0.9876")


def test_tick_must_be_positive() -> None:
    with pytest.raises(ValueError, match="Tick size must be positive"):
        Price("10").quantize_to_tick(Decimal("0"))


def test_comparison_and_equality_are_type_aware() -> None:
    assert Money("10") == Money("10.0")
    assert Money("10") != Price("10")
    assert Money("10") < Money("11")
    assert max(Price("1"), Price("2")) == Price("2")


def test_hashable() -> None:
    assert len({Money("10"), Money("10.0"), Price("10")}) == 2
