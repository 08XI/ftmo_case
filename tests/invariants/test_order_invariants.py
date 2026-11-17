"""Order invariants. Owned by humans: agents may not edit this directory.

Property-based: any sequence of fills and cancels must keep every invariant.
"""
from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from orders.order import Order, OrderError, OrderState, Side

OPS = st.lists(
    st.one_of(
        st.tuples(st.just("fill"), st.integers(min_value=-2, max_value=12)),
        st.tuples(st.just("cancel"), st.just(0)),
    ),
    max_size=25,
)


@given(quantity=st.integers(min_value=1, max_value=10), ops=OPS)
def test_invariants_hold_for_any_sequence(quantity, ops):
    order = Order("o-1", Side.BUY, Decimal(quantity))
    for op, amount in ops:
        before = (order.filled, order.state)
        try:
            if op == "fill":
                order.fill(Decimal(amount))
            else:
                order.cancel()
        except OrderError:
            assert (order.filled, order.state) == before, "a rejected operation must not mutate the order"
            continue
        filled_before, state_before = before
        assert Decimal(0) <= order.filled <= order.quantity, "filled never exceeds quantity"
        assert order.filled >= filled_before, "filled never decreases"
        assert (order.state is OrderState.FILLED) == (order.filled == order.quantity), "FILLED iff fully filled"
        assert state_before not in (OrderState.FILLED, OrderState.CANCELLED), "terminal states stay terminal"
        if op == "cancel":
            assert order.filled == filled_before, "cancel never changes filled quantity"
