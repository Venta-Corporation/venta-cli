
#!/usr/bin/env python3

import argparse
import getpass
import json
import os
import sys
import time
import base64
import hashlib
import secrets
import subprocess
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlencode, quote

# =========================================================
# VENTA CLI | PHANTOM HUB
# =========================================================

VERSION = "1.1.0"
APP_NAME = "VENTA CLI"

# ---------------------------------------------------------
# FIREBASE APPLICATION CONFIGURATION
# ---------------------------------------------------------

// Import the functions you need from the SDKs you need
import { initializeApp } from "firebase/app";
import { getAnalytics } from "firebase/analytics";
// TODO: Add SDKs for Firebase products that you want to use
// https://firebase.google.com/docs/web/setup#available-libraries

// Your web app's Firebase configuration
// For Firebase JS SDK v7.20.0 and later, measurementId is optional
const firebaseConfig = {
  apiKey: "AIzaSyBWA-zRkPFH4svRjkMUO80TUdI9zIm5ICc",
  authDomain: "phantom-messaging-a5bf0.firebaseapp.com",
  databaseURL: "https://phantom-messaging-a5bf0-default-rtdb.firebaseio.com",
  projectId: "phantom-messaging-a5bf0",
  storageBucket: "phantom-messaging-a5bf0.firebasestorage.app",
  messagingSenderId: "475147330421",
  appId: "1:475147330421:web:6fe73f781a9dbf443ca93c",
  measurementId: "G-1974SDM4VW"
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);
const analytics = getAnalytics(app);

FIREBASE_API_KEY = "AIzaSyBWA-zRkPFH4svRjkMUO80TUdI9zIm5ICc"
FIREBASE_PROJECT_ID = "phantom-messaging-a5bf0"
FIREBASE_AUTH_DOMAIN = "phantom-messaging-a5bf0.firebaseapp.com"
FIREBASE_DATABASE_URL = (
    "https://phantom-messaging-a5bf0-default-rtdb.firebaseio.com"
)
FIREBASE_APP_ID = "1:475147330421:web:6fe73f781a9dbf443ca93c"
FIREBASE_MESSAGING_SENDER_ID = "G-1974SDM4VW"

# ---------------------------------------------------------
# TERMINAL COLORS
# ---------------------------------------------------------

GREEN = "\033[92m"
CYAN = "\033[96m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
WHITE = "\033[97m"
DIM = "\033[2m"
RESET = "\033[0m"

# ---------------------------------------------------------
# CONFIGURATION STORAGE
# ---------------------------------------------------------

CONFIG_DIR = Path.home() / ".venta"
CONFIG_FILE = CONFIG_DIR / "config.json"

# ---------------------------------------------------------
# BANNER
# ---------------------------------------------------------

BANNER = r"""
 __   _____ _  _ _____  _      ___  _    ___
 \ \ / / __| \| |_   _|/_\    / __|| |  |_ _|
  \ V /| _|| .` | | | / _ \  | (__ | |__ | |
   \_/ |___|_|\_| |_|/_/ \_\  \___||____|___|

       PHANTOM MESSAGING ADMIN CONSOLE
                  VENTA CLI
"""


# =========================================================
# UI UTILITIES
# =========================================================

def line():
    print(f"{DIM}{'─' * 56}{RESET}")


def success(message):
    print(f"{GREEN}[+] {message}{RESET}")


def info(message):
    print(f"{CYAN}[*] {message}{RESET}")


def warning(message):
    print(f"{YELLOW}[!] {message}{RESET}")


def error(message):
    print(f"{RED}[-] {message}{RESET}")


def title(text):
    print()
    line()
    print(f"{CYAN}{text.center(56)}{RESET}")
    line()


def pause():
    try:
        input("\nPress Enter to continue...")
    except (KeyboardInterrupt, EOFError):
        pass


# =========================================================
# CONFIGURATION MANAGEMENT
# =========================================================

def get_config():
    if not CONFIG_FILE.exists():
        return {}

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)

        return data if isinstance(data, dict) else {}

    except (json.JSONDecodeError, OSError):
        warning("Configuration file could not be read.")
        return {}


def save_config(data):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    config = get_config()
    config.update(data)

    with open(CONFIG_FILE, "w", encoding="utf-8") as file:
        json.dump(config, file, indent=2)

    try:
        os.chmod(CONFIG_FILE, 0o600)
    except OSError:
        pass


def clear_config():
    if CONFIG_FILE.exists():
        CONFIG_FILE.unlink()


def get_api_key(config=None):
    config = config or get_config()

    return (
        config.get("api_key")
        or (FIREBASE_API_KEY if FIREBASE_API_KEY != "YOUR_FIREBASE_WEB_API_KEY" else "")
    )


def get_database_url(config=None):
    config = config or get_config()

    return (
        config.get("db_url")
        or FIREBASE_DATABASE_URL
    )


# =========================================================
# NETWORK UTILITIES
# =========================================================

def http_json(url, method="GET", data=None, timeout=20, headers=None):
    request_headers = {
        "User-Agent": "VENTA-CLI/" + VERSION
    }

    if headers:
        request_headers.update(headers)

    payload = None

    if data is not None:
        payload = json.dumps(data).encode("utf-8")
        request_headers["Content-Type"] = "application/json"

    request = Request(
        url,
        data=payload,
        headers=request_headers,
        method=method
    )

    with urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8")

        if not raw:
            return None

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw


def firebase_error_message(exc):
    try:
        body = json.loads(exc.read().decode("utf-8"))
        return body.get("error", {}).get("message", str(exc))
    except Exception:
        return str(exc)


# =========================================================
# AUTHENTICATION
# =========================================================

def firebase_login(api_key, email, password):
    url = (
        "https://identitytoolkit.googleapis.com/v1/"
        "accounts:signInWithPassword"
        f"?key={quote(api_key)}"
    )

    payload = {
        "email": email,
        "password": password,
        "returnSecureToken": True
    }

    try:
        info("Connecting to Firebase Authentication...")

        return http_json(
            url,
            method="POST",
            data=payload,
            timeout=15
        )

    except HTTPError as exc:
        message = firebase_error_message(exc)
        error(f"Authentication failed: {message}")

        if message in (
            "INVALID_LOGIN_CREDENTIALS",
            "EMAIL_NOT_FOUND",
            "INVALID_PASSWORD"
        ):
            print("\nCheck your Firebase email and password.")

        elif message == "OPERATION_NOT_ALLOWED":
            print("Email/Password authentication is disabled.")

        elif message == "API_KEY_INVALID":
            print("The Firebase Web API key is invalid.")

        return None

    except TimeoutError:
        error("Firebase connection timed out.")
        return None

    except URLError as exc:
        error(f"Network error: {exc.reason}")
        return None

    except Exception as exc:
        error(f"Unexpected authentication error: {exc}")
        return None


def firebase_refresh(refresh_token, api_key):
    url = (
        "https://securetoken.googleapis.com/v1/token"
        f"?key={quote(api_key)}"
    )

    payload = urlencode({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }).encode("utf-8")

    request = Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "VENTA-CLI/" + VERSION
        }
    )

    try:
        with urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))

    except HTTPError as exc:
        warning(f"Token refresh failed: {firebase_error_message(exc)}")
        return {}

    except Exception:
        return {}


def refresh_saved_auth():
    config = get_config()

    refresh_token = config.get("refresh_token")
    api_key = get_api_key(config)

    if not refresh_token or not api_key:
        return config

    result = firebase_refresh(refresh_token, api_key)

    if result.get("access_token"):
        save_config({
            "id_token": result["access_token"],
            "refresh_token": result.get(
                "refresh_token", refresh_token
            )
        })

        config = get_config()

    return config


def auth_login(args):
    config = get_config()

    api_key = args.api_key or get_api_key(config)

    if not api_key:
        api_key = input("Firebase Web API Key: ").strip()

    email = args.email or input("Email: ").strip()

    password = getpass.getpass("Password: ")

    result = firebase_login(
        api_key,
        email,
        password
    )

    if not result:
        return

    save_config({
        "api_key": api_key,
        "id_token": result["idToken"],
        "refresh_token": result["refreshToken"],
        "email": result["email"],
        "uid": result["localId"],
        "db_url": FIREBASE_DATABASE_URL
    })

    title("AUTHENTICATION SUCCESSFUL")
    success(f"Logged in as {result['email']}")
    print(f"UID       : {result['localId']}")
    print(f"Config    : {CONFIG_FILE}")


def auth_status():
    config = get_config()

    title("AUTHENTICATION STATUS")

    if config.get("id_token"):
        success("Authenticated")
        print(f"Email : {config.get('email', 'Unknown')}")
        print(f"UID   : {config.get('uid', 'Unknown')}")
        print(f"File  : {CONFIG_FILE}")
    else:
        warning("Not authenticated.")
        print("Run: venta auth login")


def auth_logout():
    clear_config()
    success("Logged out. Local configuration removed.")


# =========================================================
# FIREBASE DATABASE ENGINE
# =========================================================

def firebase_db_request(path, method="GET", data=None, auth=None,
                        db_url=None, timeout=20):

    db_url = (db_url or FIREBASE_DATABASE_URL).rstrip("/")
    path = path.strip("/")

    endpoint = f"{db_url}/{path}.json" if path else f"{db_url}/.json"

    if auth:
        endpoint += "?" + urlencode({"auth": auth})

    try:
        return http_json(
            endpoint,
            method=method,
            data=data,
            timeout=timeout
        )

    except HTTPError as exc:
        error(f"Firebase HTTP {exc.code}: {firebase_error_message(exc)}")
        return None

    except URLError as exc:
        error(f"Connection error: {exc.reason}")
        return None

    except TimeoutError:
        error("Firebase request timed out.")
        return None

    except Exception as exc:
        error(f"Database request failed: {exc}")
        return None


def db_command(args):
    config = get_config()

    db_url = args.db_url or get_database_url(config)
    auth_token = args.auth or config.get("id_token")

    if not db_url:
        error("Database URL is missing.")
        return

    path = args.path

    if args.action in ("set", "push"):
        if args.data is None:
            error("--data is required for this action.")
            return

        try:
            data = json.loads(args.data)
        except json.JSONDecodeError:
            error("Invalid JSON supplied to --data.")
            return

    else:
        data = None

    methods = {
        "get": "GET",
        "set": "PUT",
        "push": "POST",
        "delete": "DELETE"
    }

    title(f"DATABASE {args.action.upper()}")

    result = firebase_db_request(
        path,
        method=methods[args.action],
        data=data,
        auth=auth_token,
        db_url=db_url
    )

    if result is not None:
        success("Request completed.")
        print(json.dumps(result, indent=2, ensure_ascii=False))


# =========================================================
# CRYPTO DEPENDENCY
# =========================================================

def ensure_crypto():
    try:
        from Crypto.Cipher import AES
        return True

    except ImportError:
        warning("PyCryptodome is not installed.")

        answer = input("Install it automatically now? [Y/n]: ").strip().lower()

        if answer in ("n", "no"):
            return False

        info("Installing PyCryptodome...")

        try:
            subprocess.check_call([
                sys.executable,
                "-m",
                "pip",
                "install",
                "pycryptodome"
            ])

            from Crypto.Cipher import AES
            success("PyCryptodome installed.")
            return True

        except Exception as exc:
            error(f"Dependency installation failed: {exc}")
            print(f"Install manually: {sys.executable} -m pip install pycryptodome")
            return False


# =========================================================
# CRYPTOJS COMPATIBILITY
# =========================================================

def evp_bytes_to_key(password, salt, key_len=32, iv_len=16):
    password = password.encode("utf-8")
    result = b""
    previous = b""

    while len(result) < key_len + iv_len:
        previous = hashlib.md5(previous + password + salt).digest()
        result += previous

    return result[:key_len], result[key_len:key_len + iv_len]


def pkcs7_pad(data, block_size=16):
    padding = block_size - len(data) % block_size
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
    from Crypto.Cipher import AES

    salt = secrets.token_bytes(8)
    key, iv = evp_bytes_to_key(password, salt)

    cipher = AES.new(key, AES.MODE_CBC, iv)

    encrypted = cipher.encrypt(
        pkcs7_pad(text.encode("utf-8"))
    )

    return base64.b64encode(
        b"Salted__" + salt + encrypted
    ).decode("utf-8")


def aes_decrypt(ciphertext, password):
    from Crypto.Cipher import AES

    raw = base64.b64decode(ciphertext)

    if raw[:8] != b"Salted__":
        raise ValueError("Unsupported encryption format")

    salt = raw[8:16]
    encrypted = raw[16:]

    key, iv = evp_bytes_to_key(password, salt)

    cipher = AES.new(key, AES.MODE_CBC, iv)

    decrypted = cipher.decrypt(encrypted)

    return pkcs7_unpad(decrypted).decode("utf-8")


# =========================================================
# PHANTOM HUB
# =========================================================

def get_chat_id(uid1, uid2):
    return "_".join(sorted([str(uid1), str(uid2)]))


def messaging_request(path, method="GET", data=None, config=None):
    config = config or get_config()

    return firebase_db_request(
        path,
        method=method,
        data=data,
        auth=config.get("id_token"),
        db_url=FIREBASE_DATABASE_URL
    )


def get_users(config):
    result = messaging_request(
        "global_users",
        config=config
    )

    return result if isinstance(result, dict) else {}


def display_name(uid, profile):
    if not isinstance(profile, dict):
        return str(uid)

    return (
        profile.get("username")
        or profile.get("name")
        or profile.get("displayName")
        or profile.get("email")
        or str(uid)
    )


def explore_users(config):
    users = get_users(config)
    my_uid = config.get("uid")

    available = [
        (uid, profile)
        for uid, profile in users.items()
        if uid != my_uid
    ]

    title("PHANTOM HUB USERS")

    if not available:
        warning("No other users found.")
        return []

    for index, (uid, profile) in enumerate(available, start=1):
        print(f"{GREEN}[{index}]{RESET} {display_name(uid, profile)}")
        print(f"    UID: {uid}")
        line()

    return available


# =========================================================
# CHAT MESSAGES
# =========================================================

def get_messages(chat_id, config):
    result = messaging_request(
        f"messages/{chat_id}",
        config=config
    )

    if not isinstance(result, dict):
        return []

    messages = []

    for key, message in result.items():
        if isinstance(message, dict):
            message["_key"] = key
            messages.append(message)

    messages.sort(key=lambda msg: msg.get("time", 0))
    return messages


def render_messages(chat_id, messages, my_uid):
    title("CONVERSATION")

    if not messages:
        print(f"{DIM}No messages in this conversation.{RESET}")
        return

    for message in messages:
        sender = message.get("sender")
        timestamp = message.get("time", 0)

        try:
            time_text = time.strftime(
                "%d %b %H:%M",
                time.localtime(timestamp / 1000)
            )
        except Exception:
            time_text = "Unknown time"

        label = "YOU" if sender == my_uid else "THEM"

        if message.get("type", "text") != "text":
            content = "[Unsupported message type]"
        else:
            try:
                content = aes_decrypt(
                    message.get("content", ""),
                    chat_id
                )
            except Exception:
                content = "[Unable to decrypt message]"

        print(f"{YELLOW}{label} | {time_text}{RESET}")
        print(content)
        line()


def send_message(chat_id, recipient_uid, text, config):
    my_uid = config.get("uid")

    if not text.strip():
        return False

    timestamp = int(time.time() * 1000)

    try:
        encrypted = aes_encrypt(text, chat_id)
    except Exception as exc:
        error(f"Encryption error: {exc}")
        return False

    # Check whether chat exists.
    chat = messaging_request(
        f"chats/{chat_id}",
        config=config
    )

    if not chat:
        chat = {
            "users": {
                my_uid: True,
                recipient_uid: True
            },
            "createdAt": timestamp
        }

        created = messaging_request(
            f"chats/{chat_id}",
            method="PUT",
            data=chat,
            config=config
        )

        if created is None:
            warning("Unable to initialize chat.")
            return False

    message = {
        "sender": my_uid,
        "type": "text",
        "content": encrypted,
        "time": timestamp,
        "status": "sent"
    }

    result = messaging_request(
        f"messages/{chat_id}",
        method="POST",
        data=message,
        config=config
    )

    if result is None:
        error("Message could not be stored.")
        return False

    # Read existing metadata to preserve unread counters.
    current_meta = messaging_request(
        f"chat_meta/{chat_id}",
        config=config
    )

    unread = {}

    if isinstance(current_meta, dict):
        unread = current_meta.get("unread", {})

    if not isinstance(unread, dict):
        unread = {}

    unread[my_uid] = 0
    unread[recipient_uid] = unread.get(recipient_uid, 0) + 1

    metadata = {
        "lastMessage": encrypted,
        "lastTime": timestamp,
        "unread": unread
    }

    messaging_request(
        f"chat_meta/{chat_id}",
        method="PATCH",
        data=metadata,
        config=config
    )

    return True


# =========================================================
# CHAT SESSION
# =========================================================

def chat_session(my_uid, recipient_uid, recipient_name, config):
    chat_id = get_chat_id(my_uid, recipient_uid)

    title(f"CHAT WITH {recipient_name}")

    print("Commands: /refresh  /help  /exit")

    messages = get_messages(chat_id, config)
    render_messages(chat_id, messages, my_uid)

    while True:
        try:
            text = input(f"{GREEN}You > {RESET}").strip()

        except (KeyboardInterrupt, EOFError):
            print("\nLeaving conversation.")
            break

        if not text:
            continue

        if text == "/exit":
            break

        if text == "/help":
            print("\n/refresh  Reload messages")
            print("/help     Show commands")
            print("/exit     Leave conversation")
            continue

        if text == "/refresh":
            config = refresh_saved_auth()
            messages = get_messages(chat_id, config)
            render_messages(chat_id, messages, my_uid)
            continue

        if send_message(chat_id, recipient_uid, text, config):
            success("Message sent.")
        else:
            warning("Message sending failed.")


# =========================================================
# MESSAGING MODULE MENU
# =========================================================

def messaging_menu():
    if not ensure_crypto():
        return

    config = refresh_saved_auth()

    if not config.get("id_token") or not config.get("uid"):
        warning("Authentication required.")
        print("Run: venta auth login")
        return

    my_uid = config["uid"]

    while True:
        title("PHANTOM MESSAGING")

        print("  1. Explore Users")
        print("  2. Open Conversation")
        print("  3. Refresh Firebase Session")
        print("  4. Logout")
        print("  5. Return")
        line()

        try:
            choice = input("VENTA > ").strip()

        except (KeyboardInterrupt, EOFError):
            print()
            return

        if choice == "1":
            explore_users(config)

        elif choice == "2":
            users = explore_users(config)

            if not users:
                continue

            try:
                selection = int(input("\nSelect user number: "))
            except (ValueError, EOFError):
                warning("Invalid selection.")
                continue

            if not 1 <= selection <= len(users):
                warning("Selection out of range.")
                continue

            uid, profile = users[selection - 1]
            name = display_name(uid, profile)

            chat_session(
                my_uid,
                uid,
                name,
                config
            )

        elif choice == "3":
            config = refresh_saved_auth()

            if config.get("id_token"):
                success("Session refreshed.")
            else:
                warning("Unable to refresh. Please log in again.")

        elif choice == "4":
            auth_logout()
            return

        elif choice == "5":
            return

        else:
            warning("Invalid menu option.")


# =========================================================
# ARGUMENT PARSER
# =========================================================

def build_parser():
    parser = argparse.ArgumentParser(
        prog="venta",
        description="VENTA CLI | Phantom Hub"
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"VENTA CLI v{VERSION}"
    )

    subparsers = parser.add_subparsers(
        dest="subcommand"
    )

    # AUTH
    auth_parser = subparsers.add_parser(
        "auth",
        help="Authentication tools"
    )

    auth_sub = auth_parser.add_subparsers(
        dest="auth_action"
    )

    login_parser = auth_sub.add_parser(
        "login",
        help="Sign in to Phantom Hub"
    )

    login_parser.add_argument(
        "--api-key",
        help="Firebase Web API key"
    )

    login_parser.add_argument(
        "--email",
        help="Account email"
    )

    auth_sub.add_parser(
        "status",
        help="Show login status"
    )

    auth_sub.add_parser(
        "logout",
        help="Sign out"
    )

    # DATABASE
    db_parser = subparsers.add_parser(
        "db",
        help="Firebase database operations"
    )

    db_parser.add_argument(
        "action",
        choices=["get", "set", "push", "delete"]
    )

    db_parser.add_argument(
        "--db-url",
        help="Database URL"
    )

    db_parser.add_argument(
        "--path",
        default="/",
        help="Database path"
    )

    db_parser.add_argument(
        "--data",
        help="JSON data"
    )

    db_parser.add_argument(
        "--auth",
        help="Override authentication token"
    )

    # MESSAGING
    subparsers.add_parser(
        "messaging",
        help="Launch Phantom Messaging"
    )

    return parser


# =========================================================
# MAIN
# =========================================================

def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.subcommand:
        print(f"{CYAN}{BANNER}{RESET}")
        parser.print_help()
        return

    if args.subcommand == "auth":

        if args.auth_action == "login":
            auth_login(args)

        elif args.auth_action == "status":
            auth_status()

        elif args.auth_action == "logout":
            auth_logout()

        else:
            parser.parse_args(["auth", "--help"])

    elif args.subcommand == "db":
        db_command(args)

    elif args.subcommand == "messaging":
        messaging_menu()


if __name__ == "__main__":
    main()
