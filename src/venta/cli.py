#!/usr/bin/env python3
import argparse
import getpass
import json
import os
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BANNER = r"""
 __   _____ _  _ _____  _       ___  _    ___ 
 \ \ / / __| \| |_   _|/_\     / __|| |  |_ _|
  \ V /| _|| .` | | | / _ \   | (__ | |__ | | 
   \_/ |___|_|\_| |_|/_/ \_\   \___||____|___|
      || Phantom Messaging Admin Console ||
"""

CONFIG_DIR = Path.home() / ".venta"
CONFIG_FILE = CONFIG_DIR / "config.json"


def get_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}


def save_config(data: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    current = get_config()
    current.update(data)
    with open(CONFIG_FILE, "w") as f:
        json.dump(current, f, indent=2)
    # Secure permissions: readable/writable only by the owner
    os.chmod(CONFIG_FILE, 0o600)


def clear_config() -> None:
    if CONFIG_FILE.exists():
        CONFIG_FILE.unlink()


def firebase_login(api_key: str, email: str, password: str) -> dict:
    """Authenticates against Firebase Auth REST API."""
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={api_key}"
    payload = json.dumps(
        {"email": email, "password": password, "returnSecureToken": True}
    ).encode("utf-8")

    req = Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )

    try:
        with urlopen(req) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as e:
        body = json.loads(e.read().decode("utf-8"))
        error_msg = body.get("error", {}).get("message", e.reason)
        print(f"\n[-] Auth Error: {error_msg}", file=sys.stderr)
        sys.exit(1)
    except URLError as e:
        print(f"\n[-] Network Error: {e.reason}", file=sys.stderr)
        sys.exit(1)


def make_request(
    url: str, method: str = "GET", data: dict = None, auth: str = None
) -> None:
    full_url = f"{url}?auth={auth}" if auth else url
    headers = {"User-Agent": "VentaCLI/1.0"}
    payload = None

    if data is not None:
        payload = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = Request(full_url, data=payload, headers=headers, method=method)

    try:
        with urlopen(req) as response:
            body = response.read().decode("utf-8")
            parsed = json.loads(body)
            print("\n[+] SUCCESS")
            print("----------------------------------------")
            print(json.dumps(parsed, indent=2))
            print("----------------------------------------\n")
    except HTTPError as e:
        error_body = e.read().decode("utf-8")
        print(f"\n[-] HTTP ERROR {e.code}: {e.reason}", file=sys.stderr)
        print(f"Details: {error_body}\n", file=sys.stderr)
    except URLError as e:
        print(f"\n[-] CONNECTION ERROR: {e.reason}\n", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="VENTA CLI - Mobile Dev & Database Admin Engine"
    )
    subparsers = parser.add_subparsers(
        dest="subcommand", help="Available modules"
    )

    # --- Auth Subcommand ---
    auth_parser = subparsers.add_parser("auth", help="Firebase User Authentication")
    auth_sub = auth_parser.add_subparsers(dest="auth_action", help="Auth Actions")

    login_p = auth_sub.add_parser("login", help="Log in with email & password")
    login_p.add_argument("--api-key", help="Firebase Web API Key")
    login_p.add_argument("--email", help="User Email")

    auth_sub.add_parser("status", help="Show current authentication status")
    auth_sub.add_parser("logout", help="Clear saved credentials")

    # --- DB Subcommand ---
    db_parser = subparsers.add_parser(
        "db", help="Firebase Realtime Database engine"
    )
    db_parser.add_argument(
        "action",
        choices=["get", "set", "push", "delete"],
        help="CRUD action to perform",
    )
    db_parser.add_argument(
        "--db-url",
        help="Firebase Database URL (e.g., https://myproject.firebaseio.com)",
    )
    db_parser.add_argument(
        "--path", default="/", help="Database node path (e.g., /messages)"
    )
    db_parser.add_argument(
        "--data", help="JSON string data for 'set' or 'push'"
    )
    db_parser.add_argument(
        "--auth", help="Override stored token with explicit Secret/Token"
    )

    args = parser.parse_args()

    if not args.subcommand:
        print(BANNER)
        parser.print_help()
        sys.exit(1)

    config = get_config()

    # --- Handle Auth Commands ---
    if args.subcommand == "auth":
        if args.auth_action == "login":
            api_key = args.api_key or config.get("api_key")
            if not api_key:
                api_key = input("Enter Firebase Web API Key: ").strip()

            email = args.email or input("Enter Phantom Hub Email: ").strip()
            password = getpass.getpass("Enter Password: ").strip()

            print("\n[*] Authenticating with Firebase...")
            res = firebase_login(api_key, email, password)

            save_config(
                {
                    "api_key": api_key,
                    "id_token": res["idToken"],
                    "refresh_token": res["refreshToken"],
                    "email": res["email"],
                    "uid": res["localId"],
                }
            )
            print(f"\n[+] Logged in successfully as {res['email']}!")
            print(f"[+] User UID: {res['localId']}")
            print(f"[+] Session token saved to {CONFIG_FILE}\n")

        elif args.auth_action == "status":
            if config.get("id_token"):
                print("\n[+] AUTHENTICATED")
                print("----------------------------------------")
                print(f"Logged in as : {config.get('email')}")
                print(f"User UID     : {config.get('uid')}")
                print(f"Config File  : {CONFIG_FILE}")
                print("----------------------------------------\n")
            else:
                print(
                    "\n[-] NOT LOGGED IN. Run 'venta auth login' to authenticate.\n"
                )

        elif args.auth_action == "logout":
            clear_config()
            print("\n[+] Logged out. Saved credentials cleared.\n")

    # --- Handle DB Commands ---
    elif args.subcommand == "db":
        db_url = args.db_url or config.get("db_url")
        if not db_url:
            db_url = input(
                "Enter Firebase DB URL (e.g., https://phantom-messaging-a5bf0-default-rtdb.firebaseio.com): "
            ).strip()
            save_config({"db_url": db_url})

        # Use explicitly passed auth token, or fallback to saved logged-in token
        auth_token = args.auth or config.get("id_token")

        clean_url = db_url.rstrip("/")
        clean_path = args.path.strip("/")
        endpoint = (
            f"{clean_url}/{clean_path}.json"
            if clean_path
            else f"{clean_url}/.json"
        )

        if args.action == "get":
            make_request(endpoint, method="GET", auth=auth_token)

        elif args.action in ["set", "push"]:
            if not args.data:
                print(
                    "[-] ERROR: '--data' argument required for 'set' or 'push'.",
                    file=sys.stderr,
                )
                sys.exit(1)
            try:
                data_dict = json.loads(args.data)
            except json.JSONDecodeError:
                print(
                    "[-] ERROR: Provided '--data' is not valid JSON.",
                    file=sys.stderr,
                )
                sys.exit(1)

            http_method = "PUT" if args.action == "set" else "POST"
            make_request(
                endpoint, method=http_method, data=data_dict, auth=auth_token
            )

        elif args.action == "delete":
            make_request(endpoint, method="DELETE", auth=auth_token)


if __name__ == "__main__":
    main()
