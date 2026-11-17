"""Synthetic order-handling module used as the factory's sample codebase.

Public, synthetic code only. Not based on any real trading system.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum


class OrderError(Exception):
    """Raised when an operation would break an order invariant."""


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderState(str, Enum):
    NEW = "new"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"


@dataclass
class Order:
    order_id: str
    side: Side
    quantity: Decimal
    filled: Decimal = field(default=Decimal("0"))
    state: OrderState = OrderState.NEW

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise OrderError("quantity must be positive")

    @property
    def remaining(self) -> Decimal:
        return self.quantity - self.filled

    def fill(self, qty: Decimal) -> None:
        if qty <= 0:
            raise OrderError("fill quantity must be positive")
        if self.state not in (OrderState.NEW, OrderState.PARTIALLY_FILLED):
            raise OrderError(f"cannot fill order in state {self.state.value}")
        if self.filled + qty > self.quantity:
            raise OrderError("fill would exceed order quantity")
        self.filled += qty
        self.state = OrderState.FILLED if self.filled == self.quantity else OrderState.PARTIALLY_FILLED

    def cancel(self) -> None:
        if self.state not in (OrderState.NEW, OrderState.PARTIALLY_FILLED):
            raise OrderError(f"cannot cancel order in state {self.state.value}")
        self.state = OrderState.CANCELLED
