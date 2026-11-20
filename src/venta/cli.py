
#!/usr/bin/env python3
import argparse
import getpass
import json
import os
from pathlib import Path
import sys
import time
import base64
import hashlib
import secrets
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlencode

GREEN = "\033[92m"
CYAN = "\033[96m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"

VERSION = "1.0.0"
version = f"VENTA CLI v{VERSION}"

BANNER = r"""
 __   _____ _  _ _____  _      ___  _    ___
 \ \ / / __| \| |_   _|/_\    / __|| |  |_ _|
  \ V /| _|| .` | | | / _ \  | (__ | |__ | |
   \_/ |___|_|\_| |_|/_/ \_\  \___||____|___|
         Phantom Messaging Admin Console
              CLI VERSION : v1.0.0
"""

CONFIG_DIR = Path.home() / ".venta"
CONFIG_FILE = CONFIG_DIR / "config.json"

FIREBASE_DB = (
    "https://phantom-messaging-a5bf0-default-rtdb.firebaseio.com"
)


# =========================================================
# CONFIGURATION
# =========================================================

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

    os.chmod(CONFIG_FILE, 0o600)


def clear_config() -> None:
    if CONFIG_FILE.exists():
        CONFIG_FILE.unlink()


# =========================================================
# FIREBASE AUTHENTICATION
# =========================================================

def firebase_login(api_key: str, email: str, password: str) -> dict:
    """Authenticates against Firebase Auth REST API."""

    url = (
        "https://identitytoolkit.googleapis.com/v1/"
        f"accounts:signInWithPassword?key={api_key}"
    )

    payload = json.dumps({
        "email": email,
        "password": password,
        "returnSecureToken": True
    }).encode("utf-8")

    req = Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"}
    )

    try:
        with urlopen(req) as response:
            return json.loads(response.read().decode("utf-8"))

    except HTTPError as e:
        try:
            body = json.loads(e.read().decode("utf-8"))
            error_msg = body.get("error", {}).get("message", e.reason)
        except Exception:
            error_msg = e.reason

        print(f"\n{RED}[-] Auth Error: {error_msg}{RESET}", file=sys.stderr)
        sys.exit(1)

    except URLError as e:
        print(f"\n{RED}[-] Network Error: {e.reason}{RESET}", file=sys.stderr)
        sys.exit(1)


def firebase_refresh(refresh_token: str, api_key: str) -> dict:
    """Refresh Firebase authentication token."""

    url = (
        "https://securetoken.googleapis.com/v1/token?"
        f"key={api_key}"
    )

    payload = urlencode({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }).encode("utf-8")

    req = Request(
        url,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )

    try:
        with urlopen(req) as response:
            return json.loads(response.read().decode("utf-8"))

    except Exception:
        return {}


def refresh_saved_auth() -> dict:
    config = get_config()

    if not config.get("refresh_token") or not config.get("api_key"):
        return config

    result = firebase_refresh(
        config["refresh_token"],
        config["api_key"]
    )

    if result.get("id_token"):
        save_config({
            "id_token": result["id_token"],
            "refresh_token": result.get(
                "refresh_token",
                config.get("refresh_token")
            )
        })

        config = get_config()

    return config


# =========================================================
# ORIGINAL DATABASE REQUEST FUNCTION
# =========================================================

def make_request(
    url: str,
    method: str = "GET",
    data: dict = None,
    auth: str = None
) -> None:

    full_url = f"{url}?auth={auth}" if auth else url
    headers = {"User-Agent": "VentaCLI/1.0"}
    payload = None

    if data is not None:
        payload = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = Request(
        full_url,
        data=payload,
        headers=headers,
        method=method
    )

    try:
        with urlopen(req) as response:
            body = response.read().decode("utf-8")
            parsed = json.loads(body)

            print(f"{GREEN}[+] SUCCESS{RESET}")
            print("----------------------------------------")
            print(json.dumps(parsed, indent=2))
            print("----------------------------------------\n")

    except HTTPError as e:
        error_body = e.read().decode("utf-8")
        print(
            f"\n{RED}[-] HTTP ERROR {e.code}: {e.reason}{RESET}",
            file=sys.stderr
        )
        print(f"Details: {error_body}\n", file=sys.stderr)

    except URLError as e:
        print(
            f"\n{RED}[-] CONNECTION ERROR: {e.reason}{RESET}\n",
            file=sys.stderr
        )


# =========================================================
# PHANTOM HUB MESSAGING ENGINE
# =========================================================

def db_request(path, method="GET", data=None, auth=None):
    """Internal Firebase REST request for messaging."""

    path = path.strip("/")
    url = f"{FIREBASE_DB}/{path}.json"

    if auth:
        url += f"?auth={auth}"

    payload = None

    headers = {
        "User-Agent": "VentaCLI/1.0",
        "Content-Type": "application/json"
    }

    if data is not None:
        payload = json.dumps(data).encode("utf-8")

    req = Request(
        url,
        data=payload,
        headers=headers,
        method=method
    )

    try:
        with urlopen(req, timeout=20) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else None

    except HTTPError as e:
        try:
            details = e.read().decode("utf-8")
        except Exception:
            details = str(e)

        print(f"{RED}Firebase HTTP Error {e.code}: {details}{RESET}")
        return None

    except URLError as e:
        print(f"{RED}Firebase connection error: {e.reason}{RESET}")
        return None

    except Exception as e:
        print(f"{RED}Request error: {e}{RESET}")
        return None


def get_chat_id(uid1, uid2):
    """Generate the same sorted chat ID used by Phantom Hub."""

    return "_".join(sorted([str(uid1), str(uid2)]))


# =========================================================
# CRYPTOJS COMPATIBILITY
# =========================================================

def evp_bytes_to_key(password, salt, key_len=32, iv_len=16):
    """
    OpenSSL-compatible EVP_BytesToKey using MD5.
    Used for compatibility with CryptoJS passphrase AES format.
    """

    password = password.encode("utf-8")
    result = b""
    previous = b""

    while len(result) < key_len + iv_len:
        previous = hashlib.md5(previous + password + salt).digest()
        result += previous

    return result[:key_len], result[key_len:key_len + iv_len]


def pkcs7_pad(data, block_size=16):
    padding = block_size - (len(data) % block_size)
    return data + bytes([padding]) * padding


def pkcs7_unpad(data):
    if not data:
        raise ValueError("Empty encrypted data")

    padding = data[-1]

    if padding < 1 or padding > 16:
        raise ValueError("Invalid padding")

    if data[-padding:] != bytes([padding]) * padding:
        raise ValueError("Invalid padding")

    return data[:-padding]


def aes_encrypt(text, password):
    """
    CryptoJS AES passphrase-compatible encryption.
    Requires: pycryptodome
    """

    from Crypto.Cipher import AES

    salt = secrets.token_bytes(8)
    key, iv = evp_bytes_to_key(password, salt)

    cipher = AES.new(key, AES.MODE_CBC, iv)
    encrypted = cipher.encrypt(
        pkcs7_pad(text.encode("utf-8"))
    )

    result = b"Salted__" + salt + encrypted
    return base64.b64encode(result).decode("utf-8")


def aes_decrypt(ciphertext, password):
    """
    CryptoJS AES passphrase-compatible decryption.
    """

    from Crypto.Cipher import AES

    raw = base64.b64decode(ciphertext)

    if raw[:8] == b"Salted__":
        salt = raw[8:16]
        encrypted = raw[16:]
    else:
        raise ValueError("Unsupported encrypted message format")

    key, iv = evp_bytes_to_key(password, salt)

    cipher = AES.new(key, AES.MODE_CBC, iv)
    decrypted = cipher.decrypt(encrypted)

    return pkcs7_unpad(decrypted).decode("utf-8")


# =========================================================
# USER MANAGEMENT
# =========================================================

def get_users(auth_token):
    users = db_request("global_users", auth=auth_token)

    if not isinstance(users, dict):
        return {}

    return users


def user_display_name(uid, profile):
    if not isinstance(profile, dict):
        return str(uid)

    return (
        profile.get("username")
        or profile.get("name")
        or profile.get("displayName")
        or profile.get("email")
        or uid
    )


def explore_users(auth_token, my_uid):
    users = get_users(auth_token)

    if not users:
        print(f"{YELLOW}No users found.{RESET}")
        return []

    available = []

    print(f"\n{CYAN}========== PHANTOM HUB USERS =========={RESET}\n")

    for uid, profile in users.items():
        if uid == my_uid:
            continue

        name = user_display_name(uid, profile)
        email = profile.get("email", "") if isinstance(profile, dict) else ""

        available.append((uid, profile))

        print(f"{GREEN}[+] {name}{RESET}")
        print(f"    UID: {uid}")

        if email:
            print(f"    Email: {email}")

        print("----------------------------------------")

    if not available:
        print("No other users available.")

    return available


# =========================================================
# MESSAGE HANDLING
# =========================================================

def get_messages(chat_id, auth_token):
    messages = db_request(
        f"messages/{chat_id}",
        auth=auth_token
    )

    if not isinstance(messages, dict):
        return []

    result = []

    for key, message in messages.items():
        if isinstance(message, dict):
            message["_key"] = key
            result.append(message)

    result.sort(key=lambda item: item.get("time", 0))

    return result


def display_messages(chat_id, messages, my_uid):
    print(f"\n{CYAN}========== CONVERSATION =========={RESET}\n")

    for message in messages:
        sender = message.get("sender", "unknown")
        timestamp = message.get("time", 0)
        message_type = message.get("type", "text")
        content = message.get("content", "")

        try:
            timestamp_text = time.strftime(
                "%H:%M",
                time.localtime(timestamp / 1000)
            )
        except Exception:
            timestamp_text = "--:--"

        if sender == my_uid:
            label = "YOU"
        else:
            label = "THEM"

        if message_type == "text":
            try:
                text = aes_decrypt(content, chat_id)
            except Exception:
                text = "[Unable to decrypt message]"

        else:
            text = f"[Unsupported message type: {message_type}]"

        print(f"{YELLOW}[{timestamp_text}] {label}{RESET}")
        print(text)
        print("----------------------------------------")


def send_message(chat_id, recipient_uid, message_text, config):
    my_uid = config.get("uid")
    auth_token = config.get("id_token")

    if not message_text.strip():
        return False

    encrypted = aes_encrypt(message_text, chat_id)
    timestamp = int(time.time() * 1000)

    # Ensure chat exists
    chat_data = db_request(
        f"chats/{chat_id}",
        auth=auth_token
    )

    if not chat_data:
        chat_data = {
            "users": {
                my_uid: True,
                recipient_uid: True
            },
            "createdAt": timestamp
        }

        db_request(
            f"chats/{chat_id}",
            method="PUT",
            data=chat_data,
            auth=auth_token
        )

    # Store message
    message_data = {
        "sender": my_uid,
        "type": "text",
        "content": encrypted,
        "time": timestamp,
        "status": "sent"
    }

    db_request(
        f"messages/{chat_id}",
        method="POST",
        data=message_data,
        auth=auth_token
    )

    # Update metadata
    metadata = {
        "lastMessage": encrypted,
        "lastTime": timestamp,
        "unread": {
            my_uid: 0,
            recipient_uid: 1
        }
    }

    db_request(
        f"chat_meta/{chat_id}",
        method="PATCH",
        data=metadata,
        auth=auth_token
    )

    return True


# =========================================================
# CHAT SESSION
# =========================================================

def open_conversation(my_uid, recipient_uid, recipient_name, config):
    auth_token = config.get("id_token")
    chat_id = get_chat_id(my_uid, recipient_uid)

    print(f"\n{CYAN}Opening conversation with {recipient_name}{RESET}")
    print(f"Chat ID: {chat_id}")
    print("Type /exit to leave.")
    print("Type /refresh to reload messages.\n")

    messages = get_messages(chat_id, auth_token)
    display_messages(chat_id, messages, my_uid)

    while True:
        try:
            message_text = input(f"{GREEN}You > {RESET}").strip()

        except (KeyboardInterrupt, EOFError):
            print("\nLeaving conversation.")
            break

        if not message_text:
            continue

        if message_text == "/exit":
            break

        if message_text == "/refresh":
            messages = get_messages(chat_id, auth_token)
            display_messages(chat_id, messages, my_uid)
            continue

        if message_text == "/help":
            print("\nCommands:")
            print("  /refresh - Reload conversation")
            print("  /exit    - Return to messaging menu")
            print("  /help    - Show commands\n")
            continue

        if send_message(chat_id, recipient_uid, message_text, config):
            print(f"{GREEN}[+] Message sent.{RESET}")
        else:
            print(f"{RED}[-] Message could not be sent.{RESET}")



def ensure_crypto():
    try:
        from Crypto.Cipher import AES
        print(f"{GREEN}[+] Encryption library detected.{RESET}")
        return True

    except ImportError:
        print(f"{YELLOW}[*] Encryption library not found.{RESET}")
        print("[*] Installing PyCryptodome automatically...")

        import subprocess

        try:
            subprocess.check_call([
                sys.executable,
                "-m",
                "pip",
                "install",
                "pycryptodome"
            ])

            from Crypto.Cipher import AES
            print(f"{GREEN}[+] Encryption library installed successfully.{RESET}")
            return True

        except Exception as e:
            print(f"{RED}[-] Installation failed: {e}{RESET}")
            print("Install it manually using:")
            print("python -m pip install pycryptodome")
            return False


# =========================================================
# MESSAGING MENU
# =========================================================

def messaging_menu():

    if not ensure_crypto():
        return

    config = refresh_saved_auth() 
 
    if not config.get("id_token") or not config.get("uid"):
        print(f"{RED}[-] Please log in first: venta auth login{RESET}")
        return

    my_uid = config["uid"]

    while True:
        print(f"\n{CYAN}========== PHANTOM MESSAGING =========={RESET}")
        print("1. Explore Users")
        print("2. Open Conversation")
        print("3. Refresh Firebase Connection")
        print("4. Logout")
        print("5. Exit Messaging")
        print("----------------------------------------")

        try:
            choice = input("Select option: ").strip()

        except (KeyboardInterrupt, EOFError):
            print("\nExiting messaging.")
            return

        if choice == "1":
            explore_users(config["id_token"], my_uid)

        elif choice == "2":
            users = explore_users(config["id_token"], my_uid)

            if not users:
                continue

            try:
                selection = int(input("\nEnter user number: "))
            except ValueError:
                print(f"{RED}Invalid selection.{RESET}")
                continue

            if selection < 1 or selection > len(users):
                print(f"{RED}Invalid user number.{RESET}")
                continue

            recipient_uid, profile = users[selection - 1]
            recipient_name = user_display_name(recipient_uid, profile)

            open_conversation(
                my_uid,
                recipient_uid,
                recipient_name,
                config
            )

        elif choice == "3":
            config = refresh_saved_auth()

            if config.get("id_token"):
                print(f"{GREEN}[+] Firebase connection refreshed.{RESET}")
            else:
                print(f"{YELLOW}[-] Refresh failed. Please log in again.{RESET}")

        elif choice == "4":
            clear_config()
            print(f"{GREEN}[+] Logged out.{RESET}")
            return

        elif choice == "5":
            return

        else:
            print(f"{RED}Invalid option.{RESET}")


# =========================================================
# MAIN CLI
# =========================================================

def main():

    parser = argparse.ArgumentParser(
        description="VENTA CLI - Mobile Dev & Database Admin Engine"
    )

    parser.add_argument(
        "--version",
        action="version",
        version="VENTA CLI v1.0.0"
    )

    subparsers = parser.add_subparsers(
        dest="subcommand",
        help="Available modules"
    )

    # -----------------------------------------------------
    # AUTH SUBCOMMAND
    # -----------------------------------------------------

    auth_parser = subparsers.add_parser(
        "auth",
        help="Firebase User Authentication"
    )

    auth_sub = auth_parser.add_subparsers(
        dest="auth_action",
        help="Auth Actions"
    )

    login_p = auth_sub.add_parser(
        "login",
        help="Log in with email & password"
    )

    login_p.add_argument("--api-key", help="Firebase Web API Key")
    login_p.add_argument("--email", help="User Email")

    auth_sub.add_parser(
        "status",
        help="Show current authentication status"
    )

    auth_sub.add_parser(
        "logout",
        help="Clear saved credentials"
    )

    # -----------------------------------------------------
    # DB SUBCOMMAND
    # -----------------------------------------------------

    db_parser = subparsers.add_parser(
        "db",
        help="Firebase Realtime Database engine"
    )

    db_parser.add_argument(
        "action",
        choices=["get", "set", "push", "delete"],
        help="CRUD action to perform"
    )

    db_parser.add_argument(
        "--db-url",
        help="Firebase Database URL"
    )

    db_parser.add_argument(
        "--path",
        default="/",
        help="Database node path"
    )

    db_parser.add_argument(
        "--data",
        help="JSON string data for set or push"
    )

    db_parser.add_argument(
        "--auth",
        help="Override stored token"
    )

    # -----------------------------------------------------
    # MESSAGING SUBCOMMAND
    # -----------------------------------------------------

    subparsers.add_parser(
        "messaging",
        help="Open Phantom Hub messaging"
    )

    args = parser.parse_args()

    # -----------------------------------------------------
    # NO SUBCOMMAND
    # -----------------------------------------------------

    if not args.subcommand:
        print(f"{GREEN}{BANNER}{RESET}")
        parser.print_help()
        sys.exit(1)

    config = get_config()

    # -----------------------------------------------------
    # AUTH COMMANDS
    # -----------------------------------------------------

    if args.subcommand == "auth":

        if args.auth_action == "login":

            api_key = args.api_key or config.get("api_key")

            if not api_key:
                api_key = input(
                    "Enter Firebase Web API Key: "
            ).strip()

            email = args.email or input(
                "Enter Phantom Hub Email: "
            ).strip()

            password = getpass.getpass(
                "Enter Password: "
            ).strip()

            print(f"{YELLOW}[*] Authenticating with Firebase...{RESET}")

            res = firebase_login(api_key, email, password)

            save_config({
                "api_key": api_key,
                "id_token": res["idToken"],
                "refresh_token": res["refreshToken"],
                "email": res["email"],
                "uid": res["localId"]
            })

            print(f"\n{GREEN}[+] Logged in successfully as {res['email']}!{RESET}")
            print(f"{GREEN}[+] User UID: {res['localId']}{RESET}")
            print(f"{GREEN}[+] Session token saved to {CONFIG_FILE}{RESET}")

        elif args.auth_action == "status":

            if config.get("id_token"):
                print(f"\n{GREEN}[+] AUTHENTICATED{RESET}")
                print("----------------------------------------")
                print(f"Logged in as : {config.get('email')}")
                print(f"User UID     : {config.get('uid')}")
                print(f"Config File  : {CONFIG_FILE}")
                print("----------------------------------------\n")

            else:
                print(
                    "\n[-] NOT LOGGED IN. "
                    "Run 'venta auth login' to authenticate.\n"
                )

        elif args.auth_action == "logout":
            clear_config()
            print(f"\n{GREEN}[+] Logged out. Saved credentials cleared.{RESET}\n")

    # -----------------------------------------------------
    # DB COMMANDS
    # -----------------------------------------------------

    elif args.subcommand == "db":

        db_url = args.db_url or config.get("db_url")

        if not db_url:
            db_url = input(
                "Enter Firebase DB URL: "
            ).strip()

            save_config({"db_url": db_url})

        auth_token = args.auth or config.get("id_token")

        clean_url = db_url.rstrip("/")
        clean_path = args.path.strip("/")

        endpoint = (
            f"{clean_url}/{clean_path}.json"
            if clean_path
            else f"{clean_url}/.json"
        )

        if args.action == "get":
            make_request(
                endpoint,
                method="GET",
                auth=auth_token
            )

        elif args.action in ["set", "push"]:

            if not args.data:
                print(
                    "[-] ERROR: '--data' argument required "
                    "for 'set' or 'push'.",
                    file=sys.stderr
                )
                sys.exit(1)

            try:
                data_dict = json.loads(args.data)

            except json.JSONDecodeError:
                print(
                    f"{RED}[-] ERROR: Provided '--data' "
                    "is not valid JSON.{RESET}",
                    file=sys.stderr
                )
                sys.exit(1)

            http_method = "PUT" if args.action == "set" else "POST"

            make_request(
                endpoint,
                method=http_method,
                data=data_dict,
                auth=auth_token
            )

        elif args.action == "delete":
            make_request(
                endpoint,
                method="DELETE",
                auth=auth_token
            )

    # -----------------------------------------------------
    # MESSAGING
    # -----------------------------------------------------

    elif args.subcommand == "messaging":
        messaging_menu()


if __name__ == "__main__":
    main()
