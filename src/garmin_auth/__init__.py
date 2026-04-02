"""Garmin Connect OAuth authentication — self-healing login, refresh, and rate limit recovery."""

from importlib.metadata import version, PackageNotFoundError

from garmin_auth.auth import GarminAuth
from garmin_auth.rate_limiter import RateLimiter, rate_limited_call
from garmin_auth.storage import FileTokenStore, TokenStore

try:
    __version__ = version("garmin-auth")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"

__all__ = [
    "GarminAuth",
    "RateLimiter",
    "rate_limited_call",
    "FileTokenStore",
    "TokenStore",
]
