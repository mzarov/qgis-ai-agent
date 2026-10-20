import unittest

from ai_agent.core.llm import retry, transport
from ai_agent.core.llm.client import ApiResponseError, ModelTimeout
from ai_agent.core.llm.turns import ModelTurn


class Feedback:
    def __init__(self, cancelled=False):
        self.cancelled = cancelled

    def isCanceled(self):
        return self.cancelled


def scripted(*outcomes):
    seen = []

    def attempt():
        outcome = outcomes[len(seen)]
        seen.append(outcome)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    return attempt, seen


class WithRetriesTest(unittest.TestCase):
    def setUp(self):
        self.slept = []

    def sleep(self, seconds):
        self.slept.append(seconds)

    def run_retries(self, attempt, **extra):
        return retry.with_retries(attempt, sleep=self.sleep, clock=lambda: 0.0, **extra)

    def test_a_429_is_retried_and_the_second_attempt_wins(self):
        attempt, seen = scripted(ApiResponseError(429, "slow down"), "ok")
        self.assertEqual(self.run_retries(attempt), "ok")
        self.assertEqual(len(seen), 2)
        self.assertAlmostEqual(sum(self.slept), retry.BACKOFF_SECONDS[0])

    def test_two_server_errors_then_success(self):
        attempt, seen = scripted(ApiResponseError(500, "x"), ApiResponseError(502, "y"), "ok")
        self.assertEqual(self.run_retries(attempt), "ok")
        self.assertEqual(len(seen), 3)
        self.assertAlmostEqual(sum(self.slept), sum(retry.BACKOFF_SECONDS[:2]))

    def test_the_last_allowed_attempt_raises(self):
        attempt, seen = scripted(*[ApiResponseError(500, "x")] * retry.MAX_ATTEMPTS)
        with self.assertRaises(ApiResponseError):
            self.run_retries(attempt)
        self.assertEqual(len(seen), retry.MAX_ATTEMPTS)

    def test_an_overloaded_model_gets_more_attempts_than_a_failing_one(self):
        for status in sorted(retry.OVERLOAD_STATUSES):
            self.slept = []
            attempt, seen = scripted(*[ApiResponseError(status, "overloaded")] * retry.MAX_OVERLOAD_ATTEMPTS)
            with self.assertRaises(ApiResponseError):
                self.run_retries(attempt)
            self.assertEqual(len(seen), retry.MAX_OVERLOAD_ATTEMPTS, status)
        self.assertAlmostEqual(sum(self.slept), sum(retry.BACKOFF_SECONDS))

    def test_an_exhausted_quota_is_not_an_overload(self):
        attempt, seen = scripted(ApiResponseError(429, '{"error": "insufficient_quota"}'), "never")
        with self.assertRaises(ApiResponseError):
            self.run_retries(attempt)
        self.assertEqual(len(seen), 1)

    def test_every_pause_is_announced_before_it_starts(self):
        busy = ApiResponseError(429, "overloaded", retry_after=14)
        attempt, _ = scripted(busy, ConnectionError("reset"), "ok")
        notices = []
        announced = []

        def sleep(seconds):
            announced.append(len(notices))

        self.assertEqual(retry.with_retries(attempt, sleep=sleep, clock=lambda: 0.0, on_retry=notices.append), "ok")
        self.assertEqual((announced[0], announced[-1]), (1, 2))
        self.assertEqual(
            notices,
            [
                retry.RetryNotice(14.0, 2, retry.MAX_OVERLOAD_ATTEMPTS, True),
                retry.RetryNotice(retry.BACKOFF_SECONDS[1], 3, retry.MAX_ATTEMPTS, False),
            ],
        )

    def test_client_errors_are_never_retried(self):
        attempt, seen = scripted(ApiResponseError(400, "bad"), "never")
        with self.assertRaises(ApiResponseError):
            self.run_retries(attempt)
        self.assertEqual(len(seen), 1)
        self.assertEqual(self.slept, [])

    def test_a_fast_connection_failure_is_retried(self):
        attempt, seen = scripted(ConnectionError("reset"), "ok")
        self.assertEqual(self.run_retries(attempt), "ok")
        self.assertEqual(len(seen), 2)

    def test_a_slow_connection_failure_is_a_timeout_not_a_blip(self):
        ticks = iter([0.0, retry.FAST_FAILURE_SECONDS + 1, 100.0, 200.0])
        attempt, seen = scripted(ConnectionError("timed out"), "never")
        with self.assertRaises(ConnectionError):
            retry.with_retries(attempt, sleep=self.sleep, clock=lambda: next(ticks))
        self.assertEqual(len(seen), 1)

    def test_a_timeout_is_never_retried_however_fast_it_came(self):
        attempt, seen = scripted(ModelTimeout("did not answer within 2 s"), "never")
        with self.assertRaises(ModelTimeout):
            self.run_retries(attempt)
        self.assertEqual(len(seen), 1)

    def test_nothing_is_retried_once_chunks_reached_the_user(self):
        attempt, seen = scripted(ApiResponseError(503, "x"), "never")
        with self.assertRaises(ApiResponseError):
            self.run_retries(attempt, delivered=lambda: 3)
        self.assertEqual(len(seen), 1)

    def test_a_cancelled_run_does_not_retry_or_sleep(self):
        attempt, seen = scripted(ApiResponseError(429, "x"), "never")
        with self.assertRaises(ApiResponseError):
            self.run_retries(attempt, feedback=Feedback(cancelled=True))
        self.assertEqual(len(seen), 1)
        self.assertEqual(self.slept, [])

    def test_the_pause_stops_as_soon_as_the_user_cancels(self):
        feedback = Feedback()
        slept = []

        def cancelling_sleep(seconds):
            slept.append(seconds)
            feedback.cancelled = True

        retry._pause(4.0, feedback, cancelling_sleep)
        self.assertEqual(slept, [retry.POLL_SECONDS])

    def test_the_chunk_guard_counts_and_forwards(self):
        forwarded = []
        guard = retry.ChunkGuard(forwarded.append)
        guard("a")
        guard("b")
        self.assertEqual((guard.delivered, forwarded), (2, ["a", "b"]))


class CallModelRetryTest(unittest.TestCase):
    def setUp(self):
        self.saved = transport._dispatch, retry.SLEEP
        retry.SLEEP = lambda seconds: None
        self.calls = 0

    def tearDown(self):
        transport._dispatch, retry.SLEEP = self.saved

    def test_call_model_survives_one_rate_limit(self):
        def fake(messages, tool_schemas, overrides, timeout, url, on_chunk=None, on_thinking=None):
            self.calls += 1
            if self.calls == 1:
                raise ApiResponseError(429, "slow down")
            return ModelTurn(text="ok")

        transport._dispatch = fake
        turn = transport.call_model([{"role": "user", "content": "hi"}], [], {"url_override": "https://api.example/v1"})
        self.assertEqual(turn.text, "ok")
        self.assertEqual(self.calls, 2)

    def test_call_model_gives_up_after_the_limit(self):
        def fake(*args, **kwargs):
            self.calls += 1
            raise ApiResponseError(503, "down")

        transport._dispatch = fake
        notices = []
        with self.assertRaises(ApiResponseError):
            transport.call_model(
                [{"role": "user", "content": "hi"}],
                [],
                {"url_override": "https://api.example/v1"},
                on_retry=notices.append,
            )
        self.assertEqual(self.calls, retry.MAX_OVERLOAD_ATTEMPTS)
        self.assertEqual([notice.attempt for notice in notices], list(range(2, retry.MAX_OVERLOAD_ATTEMPTS + 1)))


if __name__ == "__main__":
    unittest.main()
