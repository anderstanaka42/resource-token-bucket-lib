import threading
import unittest

from resource_token_bucket_lib import TokenBucket


class FakeClock:
    """
    A controllable monotonic clock. We never touch wall-clock time in tests,
    so every refill delta is exactly what we set it to.
    """

    def __init__(self, start: float = 0.0):
        self._now = start

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


class TestTokenBucketConstruction(unittest.TestCase):
    def test_defaults_to_full_capacity(self):
        clock = FakeClock()
        bucket = TokenBucket(capacity=10, rate=1, clock=clock)
        self.assertEqual(bucket.tokens(), 10)

    def test_initial_tokens_override(self):
        clock = FakeClock()
        bucket = TokenBucket(capacity=10, rate=1, clock=clock, initial=3)
        self.assertEqual(bucket.tokens(), 3)

    def test_capacity_must_be_positive(self):
        with self.assertRaises(ValueError):
            TokenBucket(capacity=0, rate=1, clock=FakeClock())

    def test_rate_must_be_positive(self):
        with self.assertRaises(ValueError):
            TokenBucket(capacity=1, rate=0, clock=FakeClock())

    def test_initial_cannot_exceed_capacity(self):
        with self.assertRaises(ValueError):
            TokenBucket(capacity=5, rate=1, clock=FakeClock(), initial=6)

    def test_initial_cannot_be_negative(self):
        with self.assertRaises(ValueError):
            TokenBucket(capacity=5, rate=1, clock=FakeClock(), initial=-1)


class TestTokenBucketConsume(unittest.TestCase):
    def test_consume_within_capacity_returns_true(self):
        clock = FakeClock()
        bucket = TokenBucket(capacity=5, rate=1, clock=clock)
        self.assertTrue(bucket.try_consume(3))
        self.assertEqual(bucket.tokens(), 2)

    def test_consume_exact_capacity_returns_true(self):
        clock = FakeClock()
        bucket = TokenBucket(capacity=5, rate=1, clock=clock)
        self.assertTrue(bucket.try_consume(5))
        self.assertEqual(bucket.tokens(), 0)

    def test_consume_more_than_available_returns_false(self):
        clock = FakeClock()
        bucket = TokenBucket(capacity=5, rate=1, clock=clock)
        self.assertFalse(bucket.try_consume(6))
        self.assertEqual(bucket.tokens(), 5)

    def test_consume_more_than_capacity_returns_false(self):
        clock = FakeClock()
        bucket = TokenBucket(capacity=5, rate=1, clock=clock)
        self.assertFalse(bucket.try_consume(100))
        self.assertEqual(bucket.tokens(), 5)

    def test_consume_zero_cost_returns_true_and_no_state_change(self):
        clock = FakeClock()
        bucket = TokenBucket(capacity=5, rate=1, clock=clock)
        self.assertTrue(bucket.try_consume(0))
        self.assertEqual(bucket.tokens(), 5)

    def test_consume_negative_cost_returns_true(self):
        clock = FakeClock()
        bucket = TokenBucket(capacity=5, rate=1, clock=clock)
        self.assertTrue(bucket.try_consume(-1))
        self.assertEqual(bucket.tokens(), 5)

    def test_successive_consumes_deplete_tokens(self):
        clock = FakeClock()
        bucket = TokenBucket(capacity=5, rate=1, clock=clock)
        self.assertTrue(bucket.try_consume(2))
        self.assertTrue(bucket.try_consume(2))
        self.assertTrue(bucket.try_consume(1))
        self.assertEqual(bucket.tokens(), 0)
        self.assertFalse(bucket.try_consume(1))


class TestTokenBucketRefill(unittest.TestCase):
    def test_refill_adds_tokens_at_fixed_rate(self):
        clock = FakeClock()
        bucket = TokenBucket(capacity=10, rate=2, clock=clock, initial=0)
        self.assertEqual(bucket.tokens(), 0)
        clock.advance(3)
        self.assertEqual(bucket.tokens(), 6)

    def test_refill_capped_at_capacity(self):
        clock = FakeClock()
        bucket = TokenBucket(capacity=10, rate=2, clock=clock, initial=0)
        clock.advance(100)
        self.assertEqual(bucket.tokens(), 10)

    def test_refill_after_partial_consume(self):
        clock = FakeClock()
        bucket = TokenBucket(capacity=10, rate=1, clock=clock)
        self.assertTrue(bucket.try_consume(8))
        self.assertEqual(bucket.tokens(), 2)
        clock.advance(3)
        self.assertEqual(bucket.tokens(), 5)

    def test_refill_does_not_advance_past_consumed_during_refill_window(self):
        clock = FakeClock()
        bucket = TokenBucket(capacity=10, rate=2, clock=clock, initial=0)
        clock.advance(2)
        self.assertEqual(bucket.tokens(), 4)
        self.assertTrue(bucket.try_consume(4))
        self.assertEqual(bucket.tokens(), 0)
        clock.advance(1)
        self.assertEqual(bucket.tokens(), 2)

    def test_no_refill_when_clock_has_not_advanced(self):
        clock = FakeClock()
        bucket = TokenBucket(capacity=10, rate=2, clock=clock, initial=5)
        self.assertEqual(bucket.tokens(), 5)
        self.assertEqual(bucket.tokens(), 5)

    def test_clock_going_backward_does_not_add_tokens(self):
        clock = FakeClock(10)
        bucket = TokenBucket(capacity=10, rate=2, clock=clock, initial=2)
        clock.advance(-5)
        self.assertEqual(bucket.tokens(), 2)

    def test_refill_then_consume_then_refill_again(self):
        clock = FakeClock()
        bucket = TokenBucket(capacity=10, rate=1, clock=clock, initial=0)
        clock.advance(5)
        self.assertTrue(bucket.try_consume(5))
        self.assertEqual(bucket.tokens(), 0)
        clock.advance(2)
        self.assertEqual(bucket.tokens(), 2)
        self.assertTrue(bucket.try_consume(2))
        self.assertEqual(bucket.tokens(), 0)


class TestTokenBucketThreading(unittest.TestCase):
    def test_concurrent_consumes_never_exceed_capacity(self):
        clock = FakeClock()
        bucket = TokenBucket(capacity=1000, rate=1, clock=clock, initial=1000)
        granted = []

        def worker():
            local_count = 0
            for _ in range(200):
                if bucket.try_consume(1):
                    local_count += 1
            granted.append(local_count)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(sum(granted), 1000)
        self.assertEqual(bucket.tokens(), 0)


if __name__ == "__main__":
    unittest.main()
