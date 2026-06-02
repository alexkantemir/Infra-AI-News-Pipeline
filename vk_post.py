import json
import os
import sys
import argparse
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

VK_API_URL = "https://api.vk.com/method"
VK_API_VERSION = "5.199"


def load_env(need_photo_token: bool = False) -> tuple[str, str]:
    load_dotenv()
    group_id = os.getenv("VK_GROUP_ID")
    if need_photo_token:
        token = os.getenv("VK_USER_TOKEN") or os.getenv("VK_ACCESS_TOKEN")
        if not os.getenv("VK_USER_TOKEN"):
            print("[WARN] VK_USER_TOKEN not found in .env — photo upload may fail.")
            print("[HINT] Run: py -3.13 vk_auth.py  to get a user token.")
    else:
        token = os.getenv("VK_ACCESS_TOKEN")
    missing = [k for k, v in [("VK_ACCESS_TOKEN", token), ("VK_GROUP_ID", group_id)] if not v]
    if missing:
        print(f"[ERROR] Missing in .env: {', '.join(missing)}")
        sys.exit(1)
    return token, group_id


def vk_call(method: str, params: dict, token: str) -> dict:
    params["access_token"] = token
    params["v"] = VK_API_VERSION
    resp = requests.post(f"{VK_API_URL}/{method}", data=params, timeout=30)
    if resp.status_code != 200:
        print(f"[ERROR] HTTP {resp.status_code} calling {method}")
        sys.exit(1)
    data = resp.json()
    if "error" in data:
        err = data["error"]
        print(f"[ERROR] VK {err.get('error_code')}: {err.get('error_msg')}")
        sys.exit(1)
    return data["response"]


def get_or_create_album(token: str, group_id: str) -> int:
    albums = vk_call("photos.getAlbums", {"owner_id": f"-{group_id}", "need_system": 0}, token)
    for item in albums.get("items", []):
        if item.get("title") == "Автопостинг":
            print(f"[INFO] Using existing album id={item['id']}")
            return item["id"]
    print(f"[INFO] Creating album 'Автопостинг'...")
    album = vk_call("photos.createAlbum", {
        "title": "Автопостинг",
        "group_id": group_id,
        "privacy_view": "list,-{group_id}",
    }, token)
    print(f"[INFO] Album created id={album['id']}")
    return album["id"]


def upload_photo(image_path: Path, token: str, group_id: str) -> str:
    album_id = get_or_create_album(token, group_id)

    print(f"[INFO] Getting upload server...")
    server = vk_call("photos.getUploadServer", {"album_id": album_id, "group_id": group_id}, token)

    print(f"[INFO] Uploading {image_path.name}...")
    with open(image_path, "rb") as f:
        mime = "image/jpeg" if image_path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
        resp = requests.post(server["upload_url"], files={"file1": (image_path.name, f, mime)}, timeout=60)
    if resp.status_code != 200:
        print(f"[ERROR] Upload failed: HTTP {resp.status_code}")
        sys.exit(1)
    upload_data = resp.json()

    print(f"[INFO] Saving photo...")
    saved = vk_call("photos.save", {
        "album_id": album_id,
        "group_id": group_id,
        "server": upload_data["server"],
        "photos_list": upload_data["photos_list"],
        "hash": upload_data["hash"],
    }, token)

    photo = saved[0]
    attachment = f"photo{photo['owner_id']}_{photo['id']}"
    print(f"[OK] Photo ready: {attachment}")
    return attachment


def post_to_wall(content: str, token: str, group_id: str,
                 attachment: str | None = None,
                 schedule: str | None = None) -> int:
    params = {
        "owner_id": f"-{group_id}",
        "from_group": 1,
        "message": content,
    }
    if attachment:
        params["attachments"] = attachment
    if schedule:
        dt = datetime.fromisoformat(schedule.replace("Z", "+00:00"))
        params["publish_date"] = int(dt.timestamp())

    resp = vk_call("wall.post", params, token)
    return resp["post_id"]


def read_vk_content(json_path: Path) -> str:
    if not json_path.exists():
        print(f"[ERROR] File not found: {json_path}")
        sys.exit(1)
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
    content = data.get("platforms", {}).get("vk", {}).get("content")
    if not content:
        print("[ERROR] 'platforms.vk.content' not found in JSON")
        sys.exit(1)
    return content


def main():
    parser = argparse.ArgumentParser(
        description="Post to VK group",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python vk_post.py --json post/content.json
  python vk_post.py --json post/content.json --image post/photo.png
  python vk_post.py --content "Hello!" --image post/photo.png
  python vk_post.py --json post/content.json --image post/photo.png --schedule 2026-06-02T15:00:00Z
        """,
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--json", type=Path, metavar="FILE",
                        help="Social-content JSON (reads platforms.vk.content)")
    source.add_argument("--content", type=str, help="Post text directly")
    parser.add_argument("--image", type=Path, help="Image file to upload and attach (requires VK_USER_TOKEN)")
    parser.add_argument("--attachment", type=str, metavar="ATTACH",
                        help="Pre-existing VK attachment string, e.g. photo-239278918_12345")
    parser.add_argument("--schedule", type=str, metavar="ISO8601",
                        help="Publish date, e.g. 2026-06-02T15:00:00Z (omit for immediate)")
    args = parser.parse_args()

    token, group_id = load_env(need_photo_token=bool(args.image))

    content = read_vk_content(args.json) if args.json else args.content

    attachment = None
    if args.attachment:
        attachment = args.attachment
        print(f"[INFO] Using attachment: {attachment}")
    elif args.image:
        if not args.image.exists():
            print(f"[ERROR] Image not found: {args.image}")
            sys.exit(1)
        attachment = upload_photo(args.image, token, group_id)

    post_id = post_to_wall(content, token, group_id, attachment, args.schedule)

    label = "Scheduled" if args.schedule else "Published"
    print(f"[OK] {label}: https://vk.com/wall-{group_id}_{post_id}")


if __name__ == "__main__":
    main()
