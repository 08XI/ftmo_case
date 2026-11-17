I read the order module. Cancelling is currently only allowed from NEW; a partially filled order cannot be cancelled even though the remainder is still open. The change is small and stays inside the cancel() state check.

```json
{"summary": "Let cancel() accept PARTIALLY_FILLED orders and cancel only the remaining quantity; filled quantity is unchanged.",
 "steps": ["In orders/order.py, allow cancel() from NEW and PARTIALLY_FILLED", "Keep FILLED and CANCELLED terminal", "Add behaviour tests in tests/orders/test_order.py"],
 "invariants_affected": ["cancel never changes filled quantity", "FILLED and CANCELLED are terminal", "a rejected operation does not mutate the order"],
 "test_plan": ["partial fill then cancel keeps filled and sets CANCELLED", "cancel of a FILLED order is rejected"],
 "risks": ["Downstream consumers may assume CANCELLED implies filled == 0"]}
```
