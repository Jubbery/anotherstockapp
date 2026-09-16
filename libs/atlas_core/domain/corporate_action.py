"""Corporate actions, carrying both when they happened and when we learned it.

R-6.4.a: anything restatable records ``effective_at`` (when the fact became true
in the world) and ``knowledge_at`` (when Atlas learned it). Historical queries
filter on the latter. Without that column, a backtest uses a split it could not
have known about, and the resulting price series is one no contemporaneous
observer ever saw.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from atlas_core.domain.money import Money
from atlas_core.domain.time import ensure_utc

__all__ = ["ActionType", "CorporateAction"]


class ActionType(StrEnum):
    SPLIT = "split"
    DIVIDEND = "dividend"
    MERGER = "merger"
    SPINOFF = "spinoff"
    SYMBOL_CHANGE = "symbol_change"


@dataclass(frozen=True, slots=True)
class CorporateAction:
    """One corporate action.

    ``ratio`` is new shares per old share: ``10`` for a 10-for-1 split,
    ``Decimal("0.1")`` for a 1-for-10 reverse split.
    """

    symbol: str
    action_type: ActionType
    effective_at: date
    knowledge_at: datetime
    ratio: Decimal | None = None
    cash_amount: Money | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "knowledge_at", ensure_utc(self.knowledge_at, field="knowledge_at")
        )
        if self.action_type is ActionType.SPLIT:
            if self.ratio is None:
                raise ValueError(f"{self.symbol}: split requires a ratio")
            if self.ratio <= 0:
                raise ValueError(f"{self.symbol}: split ratio must be positive, got {self.ratio}")
        if self.action_type is ActionType.DIVIDEND and self.cash_amount is None:
            raise ValueError(f"{self.symbol}: dividend requires a cash_amount")

    @property
    def is_reverse_split(self) -> bool:
        """Reverse splits deserve attention: they are common in distressed names.

        A stock that reverse-splits 1-for-10 to regain listing compliance looks,
        in a naively adjusted series, like a stock that rose 900%. Stage A rule
        A6 excludes names with a pending action for exactly this reason.
        """
        return self.action_type is ActionType.SPLIT and self.ratio is not None and self.ratio < 1
