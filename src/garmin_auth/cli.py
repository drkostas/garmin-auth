"""CLI for garmin-auth: login, status, refresh."""

from __future__ import annotations

import argparse
import getpass
import json
import logging
import os
import sys
from pathlib import Path

from garmin_auth.auth import GarminAuth
from garmin_auth.storage import FileTokenStore

CONFIG_DIR = Path("~/.garmin-auth").expanduser()
CONFIG_FILE = CONFIG_DIR / "config.json"


def _load_config() -> dict:
    """Load saved config (email, token_dir)."""
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_config(config: dict) -> None:
    """Save config to disk."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, indent=2))


def _resolve_email(args: argparse.Namespace) -> str:
    """Resolve email from: CLI flag → env var → saved config → interactive prompt."""
    email = args.email or os.environ.get("GARMIN_EMAIL") or _load_config().get("email") or ""
    if not email:
        email = input("Garmin email: ").strip()
    return email


def _resolve_password(args: argparse.Namespace) -> str:
    """Resolve password from: CLI flag → env var → interactive prompt."""
    password = args.password or os.environ.get("GARMIN_PASSWORD") or ""
    if not password:
        password = getpass.getpass("Garmin password: ")
    return password


def _prompt_mfa() -> str:
    """Blocking prompt for the MFA code on stdin."""
    return input("Garmin MFA code: ").strip()


def _build_auth(args: argparse.Namespace, need_credentials: bool = False) -> GarminAuth:
    """Build GarminAuth from CLI args + env vars + config + interactive prompts."""
    store = FileTokenStore(args.token_dir)

    email = ""
    password = ""
    if need_credentials:
        email = _resolve_email(args)
        password = _resolve_password(args)
    else:
        email = args.email or os.environ.get("GARMIN_EMAIL") or _load_config().get("email") or ""
        password = args.password or os.environ.get("GARMIN_PASSWORD") or ""

    return GarminAuth(
        email=email,
        password=password,
        store=store,
        token_dir=args.token_dir or "~/.garminconnect",
        prompt_mfa=_prompt_mfa,
    )


def cmd_login(args: argparse.Namespace) -> None:
    """Login to Garmin Connect and save tokens."""
    auth = _build_auth(args, need_credentials=True)
    client = auth.login()
    if client == "needs_mfa":
        # Shouldn't happen in CLI mode — we passed a blocking prompt_mfa callback.
        print("✗ Unexpected MFA state. This is a bug; please file an issue.", file=sys.stderr)
        sys.exit(1)

    # Save email for next time
    config = _load_config()
    if auth.email and auth.email != config.get("email"):
        config["email"] = auth.email
        _save_config(config)

    print(f"\n✓ Authenticated as: {client.display_name}")
    print(f"  Tokens saved to: {args.token_dir}")
    if config.get("email"):
        print(f"  Email saved to: {CONFIG_FILE}")


def cmd_status(args: argparse.Namespace) -> None:
    """Check current token status."""
    auth = _build_auth(args)
    result = auth.status()

    if result["status"] == "no_tokens":
        print("✗ No tokens found. Run: garmin-auth login")
        sys.exit(1)
    else:
        print("✓ Tokens present in store")
        print(f"  Store: {result['store_type']}")
        if args.verbose:
            print(json.dumps(result, indent=2))


def cmd_refresh(args: argparse.Namespace) -> None:
    """Refresh the DI token via garminconnect's proactive refresh path."""
    auth = _build_auth(args, need_credentials=False)
    try:
        result = auth.refresh()
    except RuntimeError:
        # Cached refresh failed — fall back to full login with credentials
        print("Token refresh failed. Credentials needed for full re-login.")
        auth = _build_auth(args, need_credentials=True)
        client = auth.login()
        if client == "needs_mfa":
            print("✗ Unexpected MFA state during refresh fallback.", file=sys.stderr)
            sys.exit(1)
        result = {"status": "refreshed", "display_name": client.display_name}

    if result["status"] == "refreshed":
        name = result.get("display_name") or "unknown"
        print(f"✓ Token refreshed (account: {name})")
    else:
        print(f"✗ Refresh returned unexpected status: {result}")
        sys.exit(1)

    if args.verbose:
        print(json.dumps(result, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="garmin-auth",
        description="Garmin Connect OAuth authentication — login, refresh, and status",
    )
    parser.add_argument("--email", help="Garmin email (or GARMIN_EMAIL env var)")
    parser.add_argument("--password", help="Garmin password (or GARMIN_PASSWORD env var)")
    parser.add_argument(
        "--token-dir",
        default="~/.garminconnect",
        help="Token storage directory (default: ~/.garminconnect)",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")
    parser.add_argument("-q", "--quiet", action="store_true", help="Suppress all logging")

    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("login", help="Login and save tokens")
    subparsers.add_parser("status", help="Check token status")
    subparsers.add_parser("refresh", help="Refresh tokens if needed")

    args = parser.parse_args()

    # No command → show help
    if not args.command:
        parser.print_help()
        sys.exit(0)

    # Configure logging
    level = logging.DEBUG if args.verbose else (logging.CRITICAL if args.quiet else logging.INFO)
    logging.basicConfig(format="%(message)s", level=level)

    try:
        commands = {"login": cmd_login, "status": cmd_status, "refresh": cmd_refresh}
        commands[args.command](args)
    except RuntimeError as e:
        print(f"\n✗ Error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(130)


if __name__ == "__main__":
    main()
