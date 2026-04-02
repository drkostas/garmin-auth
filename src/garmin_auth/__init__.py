"""Garmin Connect OAuth authentication — self-healing login, refresh, and rate limit recovery."""

from garmin_auth.auth import GarminAuth
from garmin_auth.storage import FileTokenStore, DBTokenStore

__version__ = "0.1.0"
__all__ = ["GarminAuth", "FileTokenStore", "DBTokenStore"]
