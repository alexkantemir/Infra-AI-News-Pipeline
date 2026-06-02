import argparse
import json
import os
import base64
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

API_URL = "https://api.proxyapi.ru/openai/v1/images/generations"

_DEFAULT_JSON = Path("./post/2026-02-27-perplexity-computer-social-content.json")
_DEFAULT_OUTPUT = Path("./post/2026-02-27-perplexity-computer.png")


def parse_args() -> tuple[Path, Path]:
    parser = argparse.ArgumentParser(description="Generate image from social-content JSON")
    parser.add_argument("--json", type=Path, default=_DEFAULT_JSON, dest="json_path",
                        help="Path to social-content JSON")
    parser.add_argument("--output", type=Path, default=None,
                        help="Output image path (default: derived from JSON filename)")
    args = parser.parse_args()
    output = args.output
    if output is None:
        output = args.json_path.with_name(
            args.json_path.stem.replace("-social-content", "") + ".png"
        )
    return args.json_path, output


def load_env() -> tuple[str, str]:
    load_dotenv()
    missing = []
    api_key = os.getenv("PROXY_API_KEY")
    model = os.getenv("PROXY_IMAGE_MODEL")
    if not api_key:
        missing.append("PROXY_API_KEY")
    if not model:
        missing.append("PROXY_IMAGE_MODEL")
    if missing:
        print(f"[ERROR] Missing required variables in .env: {', '.join(missing)}")
        sys.exit(1)
    return api_key, model


def read_image_prompt(path: Path) -> str:
    if not path.exists():
        print(f"[ERROR] JSON file not found: {path}")
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    prompt = data.get("image_prompt")
    if not prompt:
        print("[ERROR] Field 'image_prompt' is missing or empty in the JSON file.")
        sys.exit(1)
    return prompt


def generate_image(api_key: str, model: str, prompt: str) -> dict:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "prompt": prompt,
        "n": 1,
    }
    response = requests.post(API_URL, headers=headers, json=payload, timeout=120)
    if response.status_code != 200:
        print(f"[ERROR] API returned HTTP {response.status_code}")
        try:
            detail = response.json()
            print(f"[ERROR] Response: {json.dumps(detail, ensure_ascii=False, indent=2)}")
        except Exception:
            print(f"[ERROR] Raw response: {response.text[:500]}")
        sys.exit(1)
    return response.json()


def save_image(api_response: dict, output_path: Path) -> None:
    data = api_response.get("data", [])
    if not data:
        print("[ERROR] API response contains no image data.")
        sys.exit(1)

    item = data[0]
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if "b64_json" in item and item["b64_json"]:
        image_bytes = base64.b64decode(item["b64_json"])
        output_path.write_bytes(image_bytes)
        print(f"[OK] Image saved from base64: {output_path}")
    elif "url" in item and item["url"]:
        url = item["url"]
        print(f"[INFO] Downloading image from URL...")
        img_response = requests.get(url, timeout=60)
        if img_response.status_code != 200:
            print(f"[ERROR] Failed to download image: HTTP {img_response.status_code}")
            sys.exit(1)
        output_path.write_bytes(img_response.content)
        print(f"[OK] Image saved from URL: {output_path}")
    else:
        print("[ERROR] API response contains neither 'b64_json' nor 'url'.")
        print(f"[DEBUG] item keys: {list(item.keys())}")
        sys.exit(1)


def main():
    json_path, output_path = parse_args()
    api_key, model = load_env()
    prompt = read_image_prompt(json_path)

    print(f"[INFO] Model : {model}")
    print(f"[INFO] Prompt: {prompt[:80]}...")
    print("[INFO] Sending request to ProxyAPI...")

    api_response = generate_image(api_key, model, prompt)
    save_image(api_response, output_path)

    size = output_path.stat().st_size
    print(f"[INFO] File size: {size:,} bytes")


if __name__ == "__main__":
    main()
