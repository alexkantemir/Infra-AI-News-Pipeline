"""
Content factory pipeline:
  URL -> JSON -> image -> Telegram (with image) -> VK (text only)

Usage:
  py -3.13 publish.py --url "https://example.com/article"
  py -3.13 publish.py --url "https://example.com/article" --schedule 2026-06-03T10:00:00Z
  py -3.13 publish.py --url "https://example.com/article" --dry-run
  py -3.13 publish.py --json post/existing.json --image post/existing.png
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

SKILL_PATH = Path("infra-ai-news-to-social.md")
POST_DIR = Path("post")
PROXY_OPENAI_URL = "https://api.proxyapi.ru/openai/v1/chat/completions"
PROXY_ANTHROPIC_URL = "https://api.proxyapi.ru/anthropic/v1/messages"
PYTHON = "py -3.13".split()
UTF8_ENV = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}


# ── env ──────────────────────────────────────────────────────────────────────

def load_env() -> tuple[str, str]:
    load_dotenv()
    api_key = os.getenv("PROXY_API_KEY")
    if not api_key:
        print("[ERROR] PROXY_API_KEY missing in .env")
        sys.exit(1)
    model = os.getenv("PROXY_TEXT_MODEL", "gpt-4o-mini")
    return api_key, model


# ── step 1: generate JSON ────────────────────────────────────────────────────

def read_skill() -> str:
    if not SKILL_PATH.exists():
        print(f"[ERROR] Skill file not found: {SKILL_PATH}")
        sys.exit(1)
    text = SKILL_PATH.read_text(encoding="utf-8")
    # Strip YAML frontmatter
    return re.sub(r"^---\n.*?\n---\n", "", text, flags=re.DOTALL).strip()


def fetch_article(url: str) -> str:
    print(f"[INFO] Fetching article...")
    try:
        resp = requests.get(url, timeout=30, headers={
            "User-Agent": "Mozilla/5.0 (compatible; publish-bot/1.0)"
        })
        resp.raise_for_status()
        text = re.sub(r"<[^>]+>", " ", resp.text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:10000]
    except Exception as e:
        print(f"[WARN] Could not fetch article content: {e}")
        return f"[Содержимое недоступно, анализируй только по URL: {url}]"


def generate_json(url: str, api_key: str, model: str) -> Path:
    instructions = read_skill()
    article = fetch_article(url)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    user_message = (
        f"Дата сегодня: {today}\n\n"
        f"URL статьи: {url}\n\n"
        f"Содержимое страницы:\n{article}\n\n"
        f"ВАЖНО: ответь ТОЛЬКО валидным JSON-объектом без какого-либо текста до или после него. "
        f"Никаких пояснений, никаких markdown-блоков — только JSON."
    )

    print(f"[INFO] Generating content via {model}...")

    is_claude = model.startswith("claude")

    if is_claude:
        resp = requests.post(
            PROXY_ANTHROPIC_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": model,
                "system": instructions,
                "messages": [{"role": "user", "content": user_message}],
                "temperature": 0.3,
                "max_tokens": 4000,
            },
            timeout=120,
        )
        if resp.status_code != 200:
            print(f"[ERROR] API HTTP {resp.status_code}: {resp.text[:500]}")
            sys.exit(1)
        raw = resp.json()["content"][0]["text"]
    else:
        resp = requests.post(
            PROXY_OPENAI_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": instructions},
                    {"role": "user", "content": user_message},
                ],
                "temperature": 0.3,
                "max_tokens": 4000,
            },
            timeout=120,
        )
        if resp.status_code != 200:
            print(f"[ERROR] API HTTP {resp.status_code}: {resp.text[:500]}")
            sys.exit(1)
        raw = resp.json()["choices"][0]["message"]["content"]

    # Strip markdown code fences if present
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw.strip())

    match = re.search(r"\{[\s\S]+\}", raw)
    if not match:
        print("[ERROR] No JSON found in API response")
        print(f"[DEBUG] Response (first 500 chars):\n{raw[:500]}")
        sys.exit(1)

    data = json.loads(match.group())

    pub_date = data.get("source", {}).get("published_at", today)
    if not re.match(r"\d{4}-\d{2}-\d{2}", str(pub_date)):
        pub_date = today

    slug_raw = url.rstrip("/").split("/")[-1]
    slug = re.sub(r"[^a-z0-9]+", "-", slug_raw.lower()).strip("-")[:40]
    filename = f"{pub_date}-{slug}-social-content.json"

    POST_DIR.mkdir(exist_ok=True)
    out_path = POST_DIR / filename
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] JSON -> {out_path}")
    return out_path


# ── step 2: generate image ───────────────────────────────────────────────────

def derive_image_path(json_path: Path) -> Path:
    return json_path.with_name(json_path.stem.replace("-social-content", "") + ".png")


def generate_image(json_path: Path) -> Path:
    image_path = derive_image_path(json_path)
    print(f"[INFO] Generating image -> {image_path.name}")
    result = subprocess.run(
        [*PYTHON, "generate_image_from_json.py", "--json", str(json_path), "--output", str(image_path)],
        capture_output=True, env=UTF8_ENV,
    )
    stdout = result.stdout.decode("utf-8", errors="replace") if result.stdout else ""
    stderr = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""
    if result.returncode != 0:
        print(f"[ERROR] Image generation failed:\n{stderr}")
        sys.exit(1)
    print(stdout.strip())
    return image_path


# ── step 3 & 4: post ─────────────────────────────────────────────────────────

def run_script(label: str, cmd: list[str]):
    print(f"[INFO] {label}...")
    result = subprocess.run(cmd, capture_output=True, env=UTF8_ENV)
    stdout = result.stdout.decode("utf-8", errors="replace") if result.stdout else ""
    stderr = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""
    output = (stdout + stderr).strip()
    if result.returncode != 0:
        print(f"[ERROR] {label} failed:\n{output}")
        sys.exit(1)
    print(output)


def post_telegram(json_path: Path, image_path: Path | None):
    cmd = [*PYTHON, "tg_post.py", "--json", str(json_path)]
    if image_path and image_path.exists():
        cmd += ["--image", str(image_path)]
    run_script("Telegram", cmd)


def post_vk(json_path: Path):
    run_script("VK", [*PYTHON, "vk_post.py", "--json", str(json_path)])


# ── scheduling ───────────────────────────────────────────────────────────────

def wait_until(schedule: str):
    dt = datetime.fromisoformat(schedule.replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    delta = (dt - now).total_seconds()
    if delta <= 0:
        return
    print(f"[INFO] Waiting {int(delta // 60)}m {int(delta % 60)}s until {schedule}...")
    time.sleep(delta)


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Content factory: URL -> JSON -> image -> Telegram + VK",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  py -3.13 publish.py --url "https://techcrunch.com/article"
  py -3.13 publish.py --url "https://techcrunch.com/article" --schedule 2026-06-03T12:00:00Z
  py -3.13 publish.py --url "https://techcrunch.com/article" --dry-run
  py -3.13 publish.py --json post/existing.json --image post/existing.png
        """,
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--url", type=str, help="News article URL to process")
    source.add_argument("--json", type=Path, metavar="FILE", dest="json_file",
                        help="Skip generation, use existing JSON")
    parser.add_argument("--image", type=Path, help="Skip image generation, use existing image")
    parser.add_argument("--schedule", type=str, metavar="ISO8601",
                        help="Wait until this time before posting (e.g. 2026-06-03T12:00:00Z)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Generate content but do not post")
    args = parser.parse_args()

    api_key, text_model = load_env()

    # Step 1 — JSON
    if args.json_file:
        if not args.json_file.exists():
            print(f"[ERROR] JSON not found: {args.json_file}")
            sys.exit(1)
        json_path = args.json_file
        print(f"[INFO] Using existing JSON: {json_path}")
    else:
        json_path = generate_json(args.url, api_key, text_model)

    # Step 2 — Image
    if args.image:
        image_path = args.image
        print(f"[INFO] Using existing image: {image_path}")
    else:
        image_path = generate_image(json_path)

    if args.dry_run:
        print(f"\n[DRY RUN] Content ready, posting skipped.")
        print(f"  JSON  -> {json_path}")
        print(f"  Image -> {image_path}")
        return

    # Step 3 — Wait if scheduled
    if args.schedule:
        wait_until(args.schedule)

    # Step 4 — Post
    post_telegram(json_path, image_path)
    post_vk(json_path)

    print("\n[OK] All done!")


if __name__ == "__main__":
    main()
