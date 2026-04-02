"""Tests for rate limiter."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from garminconnect import GarminConnectTooManyRequestsError

from garmin_auth.rate_limiter import RateLimiter, rate_limited_call


class TestRateLimitedCall:
    """rate_limited_call function tests."""

    def test_succeeds_first_try(self) -> None:
        func = MagicMock(return_value="result")
        with patch("garmin_auth.rate_limiter.time.sleep"):
            result = rate_limited_call(func, "arg1", delay=0)
        assert result == "result"
        func.assert_called_once_with("arg1")

    def test_retries_on_429(self) -> None:
        func = MagicMock(side_effect=[
            GarminConnectTooManyRequestsError("429"),
            "success",
        ])
        with patch("garmin_auth.rate_limiter.time.sleep"):
            result = rate_limited_call(func, delay=0, base_wait=0)
        assert result == "success"
        assert func.call_count == 2

    def test_max_retries_exceeded(self) -> None:
        func = MagicMock(side_effect=GarminConnectTooManyRequestsError("429"))
        with patch("garmin_auth.rate_limiter.time.sleep"):
            with pytest.raises(GarminConnectTooManyRequestsError, match="Max retries"):
                rate_limited_call(func, max_retries=3, delay=0, base_wait=0)
        assert func.call_count == 3

    def test_non_429_exception_not_retried(self) -> None:
        func = MagicMock(side_effect=ValueError("bad input"))
        with pytest.raises(ValueError, match="bad input"):
            rate_limited_call(func, delay=0)
        assert func.call_count == 1

    def test_delay_applied(self) -> None:
        func = MagicMock(return_value="ok")
        with patch("garmin_auth.rate_limiter.time.sleep") as mock_sleep:
            rate_limited_call(func, delay=2.5)
        mock_sleep.assert_called_once_with(2.5)

    def test_backoff_timing(self) -> None:
        func = MagicMock(side_effect=[
            GarminConnectTooManyRequestsError("429"),
            GarminConnectTooManyRequestsError("429"),
            "success",
        ])
        with patch("garmin_auth.rate_limiter.time.sleep") as mock_sleep:
            rate_limited_call(func, delay=0, base_wait=10, max_retries=3)
        # First retry: 1 * 10 = 10s, second retry: 2 * 10 = 20s, then success: delay=0
        calls = [c.args[0] for c in mock_sleep.call_args_list]
        assert calls == [10, 20, 0]

    def test_passes_kwargs(self) -> None:
        func = MagicMock(return_value="ok")
        with patch("garmin_auth.rate_limiter.time.sleep"):
            rate_limited_call(func, "a", "b", delay=0, key="value")
        func.assert_called_once_with("a", "b", key="value")


class TestRateLimiter:
    """RateLimiter class tests."""

    def test_call_delegates(self) -> None:
        func = MagicMock(return_value="result")
        limiter = RateLimiter(delay=0)
        with patch("garmin_auth.rate_limiter.time.sleep"):
            result = limiter.call(func, "arg1", key="val")
        assert result == "result"
        func.assert_called_once_with("arg1", key="val")

    def test_custom_config(self) -> None:
        limiter = RateLimiter(delay=0.5, max_retries=5, base_wait=15)
        assert limiter.delay == 0.5
        assert limiter.max_retries == 5
        assert limiter.base_wait == 15

    def test_respects_max_retries(self) -> None:
        func = MagicMock(side_effect=GarminConnectTooManyRequestsError("429"))
        limiter = RateLimiter(delay=0, max_retries=2, base_wait=0)
        with patch("garmin_auth.rate_limiter.time.sleep"):
            with pytest.raises(GarminConnectTooManyRequestsError):
                limiter.call(func)
        assert func.call_count == 2
