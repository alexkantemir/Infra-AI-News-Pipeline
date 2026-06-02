"""
Get a VK user token with photos+wall+groups scopes via login/password.
Saves the token to .env as VK_USER_TOKEN.
"""
import os
import sys
import getpass
from pathlib import Path

import vk_api
from dotenv import load_dotenv, set_key

ENV_PATH = Path(".env")
SCOPES = "photos,wall,groups,offline"


def save_token(token: str) -> None:
    set_key(str(ENV_PATH), "VK_USER_TOKEN", token)
    print(f"[OK] Token saved to .env as VK_USER_TOKEN")


def auth_handler():
    code = input("[2FA] Enter the code from SMS or authenticator app: ")
    return code, True


def captcha_handler(captcha):
    print(f"[CAPTCHA] Open this URL and enter the code: {captcha.get_url()}")
    code = input("[CAPTCHA] Enter captcha code: ")
    return captcha.try_again(code)


def main():
    load_dotenv()

    existing = os.getenv("VK_USER_TOKEN")
    if existing:
        overwrite = input("[INFO] VK_USER_TOKEN already exists in .env. Overwrite? (y/N): ").strip().lower()
        if overwrite != "y":
            print("[INFO] Aborted.")
            sys.exit(0)

    print("Enter your VK credentials to get a user token.")
    print("The password is not stored — only the resulting token is saved.\n")

    login = input("VK login (phone or email): ").strip()
    password = getpass.getpass("VK password: ")

    vk_session = vk_api.VkApi(
        login=login,
        password=password,
        scope=SCOPES,
        app_id=2685278,
        auth_handler=auth_handler,
        captcha_handler=captcha_handler,
    )

    try:
        vk_session.auth(token_only=True)
    except vk_api.AuthError as e:
        print(f"[ERROR] Auth failed: {e}")
        sys.exit(1)

    token = vk_session.token["access_token"]
    print(f"[OK] Authenticated successfully.")
    save_token(token)
    print("\nYou can now use --image with vk_post.py")


if __name__ == "__main__":
    main()
