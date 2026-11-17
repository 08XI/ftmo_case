# Plan for T-001: Cancel remaining quantity of partially filled orders

Allow Order.cancel() from PARTIALLY_FILLED as well as NEW. Cancelling sets state to CANCELLED and leaves `filled` untouched. FILLED and CANCELLED stay terminal, and cancel still raises OrderError from those states without mutating the order.

## Steps

1. Write the failing behaviour tests in tests/orders/test_order.py first and watch them fail (see test plan).
2. In orders/order.py, change the guard in Order.cancel() from `state is not NEW` to `state not in (NEW, PARTIALLY_FILLED)`. The error message stays the same, and the guard still raises before any mutation.
3. Do not modify `filled`, `quantity` or `remaining` in cancel(). The unfilled remainder is dropped only by moving to CANCELLED.
4. Leave fill() unchanged. It already rejects CANCELLED and FILLED orders, so a cancelled partial order cannot be filled further.
5. Run `python -m pytest -q`, including the human-owned invariant tests, and confirm everything passes.

## Invariants affected

- Filled quantity never exceeds order quantity (cancel must not alter filled).
- Filled quantity never decreases.
- Cancel never changes filled quantity.
- FILLED iff filled == quantity (a cancelled partial order must not become FILLED, and its filled stays below quantity).
- Terminal states (FILLED, CANCELLED) stay terminal: cancel on FILLED or CANCELLED must raise.
- A rejected operation never mutates the order.

## Test plan

- test_cancel_partially_filled_order: new order of 10, fill 4, cancel. Assert state is CANCELLED, filled == 4 and remaining == 6.
- test_cannot_fill_cancelled_partially_filled_order: after cancelling a partial order, fill raises OrderError and filled is unchanged.
- test_cannot_cancel_filled_order: fill the full quantity, cancel raises OrderError, state stays FILLED and filled is unchanged.
- test_cannot_cancel_twice: cancelling a CANCELLED order (from NEW and from PARTIALLY_FILLED) raises OrderError, and state and filled are unchanged.
- Existing tests (cancel NEW order, cannot fill cancelled) must still pass. Tests in tests/invariants/ must pass unedited.

## Risks

- Ambiguity: the task does not say whether a cancelled partial order should keep a non-zero `remaining`. The plan keeps `remaining = quantity - filled` and does not zero it. Confirm with the owner if downstream code expects remaining == 0 after cancel.
- Ambiguity: the task does not say whether cancelling an already CANCELLED order should be an idempotent no-op. The plan treats it as an error, because the invariant tests require terminal states to stay terminal and rejected operations not to mutate.
- The existing property-based invariant test already generates fill-then-cancel sequences, so it covers this change. The agents' own behaviour tests in tests/orders/ are not a substitute for it. No new invariant test appears necessary, but a human may want one specifically for 'cancel from PARTIALLY_FILLED keeps filled'. Agents must not write it.
- Protected paths (tests/invariants/**) must not be edited, and the .factory/tasks/ files must not be touched by hand.
