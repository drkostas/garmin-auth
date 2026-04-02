"""Garmin Connect OAuth authentication — self-healing login, refresh, and rate limit recovery."""

from garmin_auth.auth import GarminAuth
from garmin_auth.rate_limiter import RateLimiter, rate_limited_call
from garmin_auth.storage import DBTokenStore, FileTokenStore, TokenStore

__version__ = "0.1.0"
__all__ = [
    "GarminAuth",
    "RateLimiter",
    "rate_limited_call",
    "FileTokenStore",
    "DBTokenStore",
    "TokenStore",
]
