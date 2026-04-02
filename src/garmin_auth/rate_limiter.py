"""Rate limit handling for Garmin Connect API calls.

Provides retry-with-backoff for 429 responses and configurable delays between calls.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, TypeVar

from garminconnect import GarminConnectTooManyRequestsError

logger = logging.getLogger("garmin_auth")

T = TypeVar("T")

# Default delay between API calls (seconds)
DEFAULT_CALL_DELAY: float = 1.0

# Default retry config for 429s
DEFAULT_MAX_RETRIES: int = 3
DEFAULT_BASE_WAIT: int = 30  # seconds, multiplied by attempt number


def rate_limited_call(
    func: Callable[..., T],
    *args: Any,
    delay: float = DEFAULT_CALL_DELAY,
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_wait: int = DEFAULT_BASE_WAIT,
    **kwargs: Any,
) -> T:
    """Call a Garmin API method with rate limiting and retry on 429.

    Args:
        func: The API method to call.
        *args: Positional arguments for func.
        delay: Seconds to wait after a successful call.
        max_retries: Maximum retry attempts on 429.
        base_wait: Base wait time in seconds (multiplied by attempt number).
        **kwargs: Keyword arguments for func.

    Returns:
        The return value of func.

    Raises:
        GarminConnectTooManyRequestsError: If max retries exceeded.
    """
    for attempt in range(max_retries):
        try:
            result = func(*args, **kwargs)
            time.sleep(delay)
            return result
        except GarminConnectTooManyRequestsError:
            wait = (attempt + 1) * base_wait
            if attempt < max_retries - 1:
                logger.warning(
                    "Rate limited (429). Waiting %ds before retry %d/%d...",
                    wait, attempt + 2, max_retries,
                )
                time.sleep(wait)
            else:
                logger.error("Rate limited (429). Max retries (%d) exceeded.", max_retries)
    raise GarminConnectTooManyRequestsError("Max retries exceeded")


class RateLimiter:
    """Configurable rate limiter for Garmin API calls.

    Usage:
        limiter = RateLimiter(delay=1.5, max_retries=5)
        activities = limiter.call(client.get_activities, 0, 10)
    """

    def __init__(
        self,
        delay: float = DEFAULT_CALL_DELAY,
        max_retries: int = DEFAULT_MAX_RETRIES,
        base_wait: int = DEFAULT_BASE_WAIT,
    ) -> None:
        self.delay = delay
        self.max_retries = max_retries
        self.base_wait = base_wait

    def call(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Execute a Garmin API call with rate limiting and retry."""
        return rate_limited_call(
            func, *args,
            delay=self.delay,
            max_retries=self.max_retries,
            base_wait=self.base_wait,
            **kwargs,
        )
