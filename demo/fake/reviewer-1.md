I reviewed the diff against the plan and the test run. The change is minimal and matches the plan.

```json
{"verdict": "approved", "summary": "Change matches the plan; cancel keeps filled quantity; FILLED stays terminal; tests cover both paths.", "findings": [{"severity": "minor", "file": "orders/order.py", "line": null, "message": "Consider exposing cancelled quantity for downstream reconciliation."}], "invariants_checked": ["cancel never changes filled quantity", "FILLED and CANCELLED are terminal", "rejected operations do not mutate"]}
```
