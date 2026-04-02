"""CLI for garmin-auth: login, status, refresh."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys

from garmin_auth.auth import GarminAuth
from garmin_auth.storage import DBTokenStore, FileTokenStore


def _build_auth(args: argparse.Namespace) -> GarminAuth:
    """Build GarminAuth from CLI args + env vars."""
    store = None
    if args.database_url or os.environ.get("DATABASE_URL"):
        db_url = args.database_url or os.environ["DATABASE_URL"]
        store = DBTokenStore(db_url)
    elif args.token_dir:
        store = FileTokenStore(args.token_dir)

    return GarminAuth(
        email=args.email or os.environ.get("GARMIN_EMAIL"),
        password=args.password or os.environ.get("GARMIN_PASSWORD"),
        store=store,
        token_dir=args.token_dir or "~/.garminconnect",
    )


def cmd_login(args: argparse.Namespace) -> None:
    """Login to Garmin Connect and save tokens."""
    auth = _build_auth(args)
    client = auth.login()
    print(f"Authenticated as: {client.display_name}")
    print(json.dumps(auth.status(), indent=2))


def cmd_status(args: argparse.Namespace) -> None:
    """Check current token status."""
    auth = _build_auth(args)
    result = auth.status()
    print(json.dumps(result, indent=2))
    if result["status"] == "expired":
        sys.exit(1)


def cmd_refresh(args: argparse.Namespace) -> None:
    """Refresh tokens (exchange or full login)."""
    auth = _build_auth(args)
    result = auth.refresh()
    print(json.dumps(result, indent=2))
    if result["status"] not in ("refreshed", "skipped"):
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="garmin-auth",
        description="Garmin Connect OAuth authentication — login, refresh, and status",
    )
    parser.add_argument("--email", help="Garmin email (or GARMIN_EMAIL env var)")
    parser.add_argument("--password", help="Garmin password (or GARMIN_PASSWORD env var)")
    parser.add_argument("--token-dir", default="~/.garminconnect", help="Token storage directory (default: ~/.garminconnect)")
    parser.add_argument("--database-url", help="PostgreSQL URL for DB token storage (or DATABASE_URL env var)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")
    parser.add_argument("-q", "--quiet", action="store_true", help="Suppress all logging")

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("login", help="Login and save tokens")
    subparsers.add_parser("status", help="Check token status")
    subparsers.add_parser("refresh", help="Refresh tokens if needed")

    args = parser.parse_args()

    # Configure logging
    level = logging.DEBUG if args.verbose else (logging.CRITICAL if args.quiet else logging.INFO)
    logging.basicConfig(format="%(message)s", level=level)

    commands = {"login": cmd_login, "status": cmd_status, "refresh": cmd_refresh}
    commands[args.command](args)


if __name__ == "__main__":
    main()
