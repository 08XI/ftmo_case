from decimal import Decimal

import pytest

from orders.order import Order, OrderError, OrderState, Side


def test_new_order_starts_unfilled():
    order = Order("o-1", Side.BUY, Decimal("10"))
    assert order.state is OrderState.NEW
    assert order.remaining == Decimal("10")


def test_partial_then_full_fill():
    order = Order("o-2", Side.SELL, Decimal("10"))
    order.fill(Decimal("4"))
    assert order.state is OrderState.PARTIALLY_FILLED
    order.fill(Decimal("6"))
    assert order.state is OrderState.FILLED
    assert order.remaining == Decimal("0")


def test_overfill_is_rejected_without_mutation():
    order = Order("o-3", Side.BUY, Decimal("5"))
    order.fill(Decimal("3"))
    with pytest.raises(OrderError):
        order.fill(Decimal("3"))
    assert order.filled == Decimal("3")


def test_cancel_new_order():
    order = Order("o-4", Side.BUY, Decimal("5"))
    order.cancel()
    assert order.state is OrderState.CANCELLED


def test_cannot_fill_cancelled_order():
    order = Order("o-5", Side.BUY, Decimal("5"))
    order.cancel()
    with pytest.raises(OrderError):
        order.fill(Decimal("1"))


def test_quantity_must_be_positive():
    with pytest.raises(OrderError):
        Order("o-6", Side.BUY, Decimal("0"))


def test_cancel_partially_filled_order_keeps_filled_quantity():
    order = Order("o-7", Side.BUY, Decimal("10"))
    order.fill(Decimal("4"))
    order.cancel()
    assert order.state is OrderState.CANCELLED
    assert order.filled == Decimal("4")


def test_cannot_cancel_filled_order():
    order = Order("o-8", Side.BUY, Decimal("2"))
    order.fill(Decimal("2"))
    with pytest.raises(OrderError):
        order.cancel()
