#!/usr/bin/env python3
import argparse
import json
import sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

BANNER = r"""
 __   _____ _  _ _____  _     ___  _    ___ 
 \ \ / / __| \| |_   _|/_\   / __|| |  |_ _|
  \ V /| _|| .` | | | / _ \ | (__ | |__ | | 
   \_/ |___|_|\_| |_|/_/ \_\ \___||____|___|
       Phantom Messaging Admin Console
"""

def make_request(url: str, method: str = "GET", data: dict = None, auth: str = None) -> None:
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
    parser = argparse.ArgumentParser(description="VENTA CLI - Mobile Dev & Database Admin Engine")
    subparsers = parser.add_subparsers(dest="subcommand", help="Available modules")

    # --- DB Module ---
    db_parser = subparsers.add_parser("db", help="Firebase Realtime Database engine")
    db_parser.add_argument("action", choices=["get", "set", "push", "delete"], help="CRUD action to perform")
    db_parser.add_argument("--db-url", required=True, help="Firebase Database URL (e.g., https://myproject.firebaseio.com)")
    db_parser.add_argument("--path", default="/", help="Database node path (e.g., /messages or /users/u1)")
    db_parser.add_argument("--data", help="JSON string data to send for 'set' or 'push'")
    db_parser.add_argument("--auth", help="Firebase Secret key or User ID Token (optional if rules are public)")

    args = parser.parse_args()

    if not args.subcommand:
        print(BANNER)
        parser.print_help()
        sys.exit(1)

    if args.subcommand == "db":
        clean_url = args.db_url.rstrip("/")
        clean_path = args.path.strip("/")
        endpoint = f"{clean_url}/{clean_path}.json" if clean_path else f"{clean_url}/.json"

        if args.action == "get":
            make_request(endpoint, method="GET", auth=args.auth)

        elif args.action in ["set", "push"]:
            if not args.data:
                print("[-] ERROR: '--data' argument required for 'set' or 'push'.", file=sys.stderr)
                sys.exit(1)
            try:
                data_dict = json.loads(args.data)
            except json.JSONDecodeError:
                print("[-] ERROR: Provided '--data' is not valid JSON. Quote strings or use format '{\"key\":\"val\"}'", file=sys.stderr)
                sys.exit(1)

            http_method = "PUT" if args.action == "set" else "POST"
            make_request(endpoint, method=http_method, data=data_dict, auth=args.auth)

        elif args.action == "delete":
            make_request(endpoint, method="DELETE", auth=args.auth)

if __name__ == "__main__":
    main()
