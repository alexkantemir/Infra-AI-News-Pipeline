import json
import os
import sys
import argparse
from pathlib import Path

import requests
from dotenv import load_dotenv

TG_API = "https://api.telegram.org/bot{token}/{method}"


def load_env() -> tuple[str, str]:
    load_dotenv()
    token = os.getenv("TG_BOT_TOKEN")
    chat_id = os.getenv("TG_CHAT_ID")
    missing = [k for k, v in [("TG_BOT_TOKEN", token), ("TG_CHAT_ID", chat_id)] if not v]
    if missing:
        print(f"[ERROR] Missing in .env: {', '.join(missing)}")
        sys.exit(1)
    return token, chat_id


def api_url(token: str, method: str) -> str:
    return TG_API.format(token=token, method=method)


def tg_call(method: str, token: str, data: dict = None, files: dict = None) -> dict:
    resp = requests.post(api_url(token, method), data=data, files=files, timeout=60)
    result = resp.json()
    if not result.get("ok"):
        print(f"[ERROR] Telegram API error: {result.get('description')}")
        sys.exit(1)
    return result["result"]


def send_text(content: str, token: str, chat_id: str) -> int:
    result = tg_call("sendMessage", token, data={
        "chat_id": chat_id,
        "text": content,
    })
    return result["message_id"]


TG_CAPTION_LIMIT = 1024


def send_photo(content: str, image_path: Path, token: str, chat_id: str) -> int:
    print(f"[INFO] Sending photo: {image_path.name}")
    mime = "image/jpeg" if image_path.suffix.lower() in (".jpg", ".jpeg") else "image/png"

    if len(content) <= TG_CAPTION_LIMIT:
        with open(image_path, "rb") as f:
            result = tg_call("sendPhoto", token, data={
                "chat_id": chat_id,
                "caption": content,
            }, files={"photo": (image_path.name, f, mime)})
        return result["message_id"]

    # Content too long — send photo first, then text
    with open(image_path, "rb") as f:
        photo_result = tg_call("sendPhoto", token, data={"chat_id": chat_id},
                               files={"photo": (image_path.name, f, mime)})
    print(f"[INFO] Photo sent (message_id={photo_result['message_id']}), sending text...")
    text_result = tg_call("sendMessage", token, data={"chat_id": chat_id, "text": content})
    return text_result["message_id"]


def read_tg_content(json_path: Path) -> str:
    if not json_path.exists():
        print(f"[ERROR] File not found: {json_path}")
        sys.exit(1)
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
    content = data.get("platforms", {}).get("telegram", {}).get("content")
    if not content:
        print("[ERROR] 'platforms.telegram.content' not found in JSON")
        sys.exit(1)
    return content


def main():
    parser = argparse.ArgumentParser(
        description="Post to Telegram channel",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tg_post.py --json post/content.json
  python tg_post.py --json post/content.json --image post/photo.png
  python tg_post.py --content "Hello!" --image post/photo.png
        """,
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--json", type=Path, metavar="FILE",
                        help="Social-content JSON (reads platforms.telegram.content)")
    source.add_argument("--content", type=str, help="Post text directly")
    parser.add_argument("--image", type=Path, help="Image file to attach")
    args = parser.parse_args()

    token, chat_id = load_env()
    content = read_tg_content(args.json) if args.json else args.content

    if args.image:
        if not args.image.exists():
            print(f"[ERROR] Image not found: {args.image}")
            sys.exit(1)
        msg_id = send_photo(content, args.image, token, chat_id)
    else:
        msg_id = send_text(content, token, chat_id)

    print(f"[OK] Published: message_id={msg_id}")


if __name__ == "__main__":
    main()
