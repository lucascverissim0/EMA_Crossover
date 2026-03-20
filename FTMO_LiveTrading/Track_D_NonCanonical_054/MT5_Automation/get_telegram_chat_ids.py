from __future__ import annotations

import argparse
import json
import os
from urllib.request import Request, urlopen


def fetch_updates(bot_token: str) -> dict:
    url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
    request = Request(url=url, method="GET")
    with urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Print numeric Telegram chat IDs seen by your bot.")
    parser.add_argument("--token-env", default="TELEGRAM_BOT_TOKEN", help="Env var containing bot token.")
    args = parser.parse_args()

    token = os.getenv(args.token_env, "")
    if not token:
        raise RuntimeError(f"Environment variable {args.token_env} is not set.")

    payload = fetch_updates(token)
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram API error: {payload}")

    updates = payload.get("result", [])
    if not updates:
        print("No updates yet. Send a message to your bot first, then rerun this script.")
        return

    seen = set()
    rows = []
    for item in updates:
        message = item.get("message") or item.get("edited_message")
        if not message:
            continue
        chat = message.get("chat", {})
        chat_id = chat.get("id")
        if chat_id is None or chat_id in seen:
            continue
        seen.add(chat_id)
        rows.append(
            {
                "chat_id": chat_id,
                "type": chat.get("type"),
                "title": chat.get("title"),
                "username": chat.get("username"),
                "first_name": chat.get("first_name"),
                "last_name": chat.get("last_name"),
            }
        )

    if not rows:
        print("No message chats found in updates.")
        return

    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()