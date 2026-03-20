from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def send_message(bot_token: str, chat_id: str, text: str) -> dict:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    body = urlencode({"chat_id": chat_id, "text": text}).encode("utf-8")
    request = Request(url=url, data=body, method="POST")
    with urlopen(request, timeout=10) as response:
        payload = response.read().decode("utf-8")
    return json.loads(payload)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send a Telegram test message using MT5 automation config.")
    parser.add_argument("--config", default="config.json", help="Path to config JSON next to the runner.")
    parser.add_argument(
        "--message",
        default="Track D MT5 Telegram setup test: alerts are working.",
        help="Custom message body.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    script_dir = Path(__file__).resolve().parent
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = script_dir / config_path

    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")

    cfg = load_json(config_path)
    tg_cfg = cfg.get("telegram", {})
    if not tg_cfg.get("enabled", False):
        raise RuntimeError("telegram.enabled is false in config.")

    bot_token_env = tg_cfg.get("bot_token_env", "TELEGRAM_BOT_TOKEN")
    bot_token = os.getenv(bot_token_env, "")
    chat_id = str(tg_cfg.get("chat_id", "")).strip()

    if not bot_token:
        raise RuntimeError(f"Environment variable {bot_token_env} is not set.")
    if not chat_id:
        raise RuntimeError("telegram.chat_id is not set in config.")

    result = send_message(bot_token, chat_id, args.message)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()