I relaxed the state check in cancel() so partially filled orders can be cancelled. I ran out of session before writing the tests.

```json
{"summary": "cancel() now accepts partially filled orders; tests not yet written.", "done": ["Relaxed state check in cancel()"], "remaining": ["Add behaviour tests for partial cancel and cancel of FILLED"], "open_questions": [], "files_touched": ["orders/order.py"], "tests": "not_run", "status": "in_progress"}
```
