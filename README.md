# resource-token-bucket-lib

A token bucket that refills at a fixed rate, consumes tokens on demand, and returns booleans for flow control under load.

```python
from resource_token_bucket_lib import TokenBucket

bucket = TokenBucket(capacity=10, rate=2.0)

if bucket.try_consume(1):
    pass  # proceed with work
else:
    pass  # shed load
```

## Why this exists

When a service needs to bound the rate of an expensive operation — outbound API
 calls, database writes, file handles — a boolean gate is usually what the
call site wants: proceed or back off. This library gives you exactly that.

The trade-off: this is a lazy, in-process limiter. Tokens are refilled on demand
when `try_consume` or `tokens` is called, not by a background thread. If nobody
asks, nobody accrues. This keeps the implementation dependency-free and avoids
timer drift, but it means the bucket is per-process — it will not coordinate
across machines or share a budget between replicas.

## The awkward edge

If you pass a clock that goes backwards (e.g. a misconfigured or mocked
time source), the bucket treats the elapsed delta as zero and does not deduct
tokens. It will not add tokens for negative elapsed time, but it also will not
throw. This is a deliberate choice: failing the call would be worse for flow
control than simply waiting for the clock to recover.

## API

- `TokenBucket(capacity, rate, clock=None, initial=None)` — construct a bucket.
  `capacity` and `rate` must be positive. `initial` defaults to `capacity` and
  must be in `[0, capacity]`. `clock` is a zero-argument callable returning a
  float; it defaults to `time.monotonic`.
- `try_consume(cost=1.0) -> bool` — attempt to consume `cost` tokens. Returns
  `True` and deducts if enough are available, `False` with no state change
  otherwise. Non-positive costs always return `True`.
- `tokens() -> float` — current available tokens, refilling lazily first.
  Capped at `capacity`.
- `capacity -> float` and `rate -> float` — read-only properties.

## Running the tests

```
PYTHONPATH=src python -m unittest discover -s tests
```
