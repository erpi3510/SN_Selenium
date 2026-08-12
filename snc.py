# -*- coding: utf-8 -*-

import os
import signal
import sys
import time

from playwright.sync_api import sync_playwright


SECRET_PATH = "/run/secrets"
DEFAULT_TARGET_PATH_SCHEDULED = "/atf_test_runner.do?sysparm_nostack=true&sysparm_scheduled_tests_only=true"
DEFAULT_TARGET_PATH_ALL = "/atf_test_runner.do?sysparm_nostack=true"
PAGE_TIMEOUT_MS = int(os.getenv("PAGE_TIMEOUT_MS", "30000"))
KEEPALIVE_SECONDS = int(os.getenv("KEEPALIVE_SECONDS", "60"))

shutdown_requested = False


def _handle_shutdown(signum, frame):
    global shutdown_requested
    shutdown_requested = True


def read_secret(secret_name: str):
    """Return a secret value from env or a Docker secret file."""
    env_names = [secret_name, secret_name.upper(), secret_name.replace("-", "_").upper()]
    for env_name in env_names:
        value = os.getenv(env_name)
        if value and value.strip():
            return value.strip()

    secret_file = os.path.join(SECRET_PATH, secret_name)
    try:
        with open(secret_file, "r", encoding="utf-8") as handle:
            value = handle.read().strip()
        if value:
            return value
    except FileNotFoundError:
        pass

    return None


def require_value(name: str, value):
    if value is None or value == "":
        raise RuntimeError(
            f"Missing required value for {name}. Set env var or Docker secret."
        )
    return value


def open_page(page, url: str, label: str):
    """Navigate to a URL and let its JavaScript execute, surfacing real errors."""
    try:
        response = page.goto(url, wait_until="networkidle", timeout=PAGE_TIMEOUT_MS)
    except Exception as exc:
        print(f"ERROR while loading {label}: {exc}")
        return None

    status = response.status if response else "unknown"
    print(f"{label}: HTTP {status} (final URL: {page.url})")
    if response is not None and not response.ok:
        print(f"ERROR: {label} returned status {status}")
    return response


def get_login_url():
    return (
        os.getenv("LOGIN_URL")
        or os.getenv("SSO_URL")
        or read_secret("login_url")
        or read_secret("sso_url")
        or read_secret("sn_login_url")
    )


def get_target_url(base_url: str):
    if os.getenv("TARGET_URL"):
        return os.getenv("TARGET_URL")

    runner_mode = os.getenv("RUNNER_MODE", "scheduled").strip().lower()
    if runner_mode in ("all", "no-schedule", "noscheduled"):
        path = DEFAULT_TARGET_PATH_ALL
    else:
        path = DEFAULT_TARGET_PATH_SCHEDULED

    return f"{base_url.rstrip('/')}{path}"


def main():
    base_url = require_value("SN_URL", read_secret("sn_url"))
    login_url = get_login_url()
    target_url = get_target_url(base_url)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = browser.new_context()
        page = context.new_page()

        try:
            if login_url:
                print("Loading SSO login URL.")
                login_response = open_page(page, login_url, "Login")
                if login_response is None or not login_response.ok:
                    print("ERROR: Login failed, skipping runner request this cycle.")
                    return 1

            runner_response = open_page(page, target_url, "Runner page")
            if runner_response is None or not runner_response.ok:
                return 1

            print(f"Runner page title: {page.title()!r}")
            try:
                os.makedirs("/app/debug", exist_ok=True)
                debug_shot = f"/app/debug/runner_{int(time.time())}.png"
                page.screenshot(path=debug_shot, full_page=True)
                print(f"Saved debug screenshot: {debug_shot}")
                body_snippet = page.inner_text("body")[:300].replace("\n", " ")
                print(f"Runner page body snippet: {body_snippet!r}")
            except Exception as exc:
                print(f"WARNING: could not capture debug info: {exc}")

            print(f"Runner page loaded. Keeping session alive (check every {KEEPALIVE_SECONDS}s).")
            while not shutdown_requested:
                time.sleep(KEEPALIVE_SECONDS)
                if shutdown_requested:
                    break
                try:
                    print(f"Keepalive: page title = {page.title()!r}")
                except Exception as exc:
                    print(f"ERROR: keepalive check failed: {exc}")
                    return 1

            print("Shutdown requested, closing browser.")
            return 0
        except Exception as exc:
            print(f"ERROR: {exc}")
            try:
                page.screenshot(path=f"/app/error_{int(time.time())}.png")
            except Exception:
                pass
            return 1
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _handle_shutdown)
    signal.signal(signal.SIGINT, _handle_shutdown)
    sys.exit(main())