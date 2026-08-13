# -*- coding: utf-8 -*-

import os
import signal
import sys
import time
from urllib.parse import urlparse

from playwright.sync_api import (
    Error as PlaywrightError,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)


SECRET_PATH = "/run/secrets"

DEFAULT_TARGET_PATH_SCHEDULED = (
    "/atf_test_runner.do?"
    "sysparm_nostack=true&"
    "sysparm_scheduled_tests_only=true"
)

DEFAULT_TARGET_PATH_ALL = (
    "/atf_test_runner.do?"
    "sysparm_nostack=true"
)

PAGE_TIMEOUT_MS = int(os.getenv("PAGE_TIMEOUT_MS", "30000"))
KEEPALIVE_SECONDS = int(os.getenv("KEEPALIVE_SECONDS", "60"))
STARTUP_TIMEOUT_SECONDS = int(os.getenv("STARTUP_TIMEOUT_SECONDS", "20"))
DEBUG_DIR = os.getenv("DEBUG_DIR", "/app/debug")

shutdown_requested = False


def _handle_shutdown(signum, frame):
    global shutdown_requested
    print(f"Shutdown signal received: {signum}", flush=True)
    shutdown_requested = True


def read_secret(secret_name: str):
    """
    Read config from environment variable or Docker secret.
    """

    env_names = [
        secret_name,
        secret_name.upper(),
        secret_name.replace("-", "_").upper(),
    ]

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
            f"Missing required value for {name}. "
            "Set environment variable or Docker secret."
        )

    return value


def get_login_url():
    """
    One-time SSO bootstrap URL.

    Example:
        https://example.service-now.com/sso?token=...
    """

    return (
        os.getenv("LOGIN_URL")
        or read_secret("login_url")
        or os.getenv("SSO_URL")
        or read_secret("sso_url")
    )


def get_target_url(base_url: str):
    explicit_target = os.getenv("TARGET_URL")

    if explicit_target:
        return explicit_target.strip()

    runner_mode = os.getenv(
        "RUNNER_MODE",
        "scheduled",
    ).strip().lower()

    if runner_mode in {
        "all",
        "no-schedule",
        "noscheduled",
    }:
        path = DEFAULT_TARGET_PATH_ALL
    else:
        path = DEFAULT_TARGET_PATH_SCHEDULED

    return f"{base_url.rstrip('/')}{path}"


def get_proxy_config():
    server = (
        os.getenv("PROXY_SERVER")
        or read_secret("proxy_server")
    )

    if not server:
        return None

    proxy = {
        "server": server,
    }

    username = (
        os.getenv("PROXY_USERNAME")
        or read_secret("proxy_username")
    )

    password = (
        os.getenv("PROXY_PASSWORD")
        or read_secret("proxy_password")
    )

    if username:
        proxy["username"] = username

    if password:
        proxy["password"] = password

    return proxy


def mask_url(url: str):
    """
    Avoid printing one-time SSO tokens into logs.
    """

    if not url:
        return url

    parsed = urlparse(url)

    if not parsed.query:
        return url

    return (
        f"{parsed.scheme}://"
        f"{parsed.netloc}"
        f"{parsed.path}"
        "?<redacted>"
    )


def same_instance(url: str, base_url: str):
    """
    Check whether a URL belongs to the configured ServiceNow host.
    """

    try:
        return (
            urlparse(url).netloc.lower()
            == urlparse(base_url).netloc.lower()
        )
    except Exception:
        return False


def setup_browser_logging(page):
    def on_console(message):
        try:
            print(
                f"BROWSER CONSOLE [{message.type}]: "
                f"{message.text}",
                flush=True,
            )
        except Exception:
            pass

    def on_page_error(error):
        print(
            f"BROWSER PAGE ERROR: {error}",
            flush=True,
        )

    def on_request_failed(request):
        try:
            print(
                "BROWSER REQUEST FAILED: "
                f"{request.method} "
                f"{mask_url(request.url)} "
                f"{request.failure}",
                flush=True,
            )
        except Exception as exc:
            print(
                f"BROWSER REQUEST FAILED: {exc}",
                flush=True,
            )

    page.on("console", on_console)
    page.on("pageerror", on_page_error)
    page.on("requestfailed", on_request_failed)


def save_debug_info(page, prefix: str):
    try:
        os.makedirs(DEBUG_DIR, exist_ok=True)

        timestamp = int(time.time())

        screenshot_path = os.path.join(
            DEBUG_DIR,
            f"{prefix}_{timestamp}.png",
        )

        page.screenshot(
            path=screenshot_path,
            full_page=True,
        )

        print(
            f"Saved debug screenshot: {screenshot_path}",
            flush=True,
        )

    except Exception as exc:
        print(
            f"WARNING: could not save screenshot: {exc}",
            flush=True,
        )

    try:
        print(
            f"Debug page URL: {mask_url(page.url)}",
            flush=True,
        )

        print(
            f"Debug page title: {page.title()!r}",
            flush=True,
        )

    except Exception as exc:
        print(
            f"WARNING: could not read page metadata: {exc}",
            flush=True,
        )

    try:
        body = page.locator("body").inner_text(
            timeout=5000,
        )

        body_snippet = (
            body[:1000]
            .replace("\r", " ")
            .replace("\n", " ")
        )

        print(
            f"Debug body snippet: {body_snippet!r}",
            flush=True,
        )

    except Exception as exc:
        print(
            f"WARNING: could not read page body: {exc}",
            flush=True,
        )


def open_page(
    page,
    url: str,
    label: str,
    redact_url: bool = False,
):
    shown_url = mask_url(url) if redact_url else url

    print("")
    print(
        f"Loading {label}: {shown_url}",
        flush=True,
    )

    try:
        response = page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=PAGE_TIMEOUT_MS,
        )

    except PlaywrightTimeoutError as exc:
        print(
            f"ERROR: timeout while loading {label}: {exc}",
            flush=True,
        )
        return None

    except PlaywrightError as exc:
        print(
            f"ERROR: Playwright error while loading "
            f"{label}: {exc}",
            flush=True,
        )
        return None

    except Exception as exc:
        print(
            f"ERROR while loading {label}: {exc}",
            flush=True,
        )
        return None

    status = response.status if response else "unknown"

    print(
        f"{label}: HTTP {status}",
        flush=True,
    )

    print(
        f"{label}: final URL: {mask_url(page.url)}",
        flush=True,
    )

    if response is not None and not response.ok:
        print(
            f"ERROR: {label} returned HTTP {status}",
            flush=True,
        )

    return response


def looks_like_login_page(page):
    """
    Conservative login-page detection.

    Do not treat generic 'sso' in the URL as failure because
    successful one-time-token flows may legitimately use /sso.
    """

    try:
        current_url = page.url.lower()
    except Exception:
        return True

    url_indicators = (
        "/login.do",
        "signin",
        "sign-in",
        "oauth_login",
        "saml_redirect",
        "authenticate",
    )

    for indicator in url_indicators:
        if indicator in current_url:
            return True

    try:
        title = page.title().lower()

        title_indicators = (
            "sign in",
            "login",
            "authentication required",
        )

        for indicator in title_indicators:
            if indicator in title:
                return True

    except Exception:
        pass

    try:
        body = page.locator("body").inner_text(
            timeout=2000
        ).lower()

        body_indicators = (
            "please sign in",
            "sign in to continue",
            "authentication required",
            "invalid credentials",
        )

        for indicator in body_indicators:
            if indicator in body:
                return True

    except Exception:
        pass

    return False


def consume_one_time_sso(page, login_url: str):
    """
    Consume LOGIN_URL exactly once.

    The URL is never revisited or retried automatically because
    the token may be single-use.
    """

    print("")
    print("=" * 70)
    print("One-time SSO bootstrap")
    print("=" * 70)

    response = open_page(
        page,
        login_url,
        "One-time SSO URL",
        redact_url=True,
    )

    if response is None:
        print(
            "ERROR: one-time SSO URL could not be loaded.",
            flush=True,
        )
        return False

    if not response.ok:
        print(
            "ERROR: one-time SSO URL returned "
            f"HTTP {response.status}.",
            flush=True,
        )
        return False

    # Allow redirects, cookie writes and client-side scripts to finish.
    page.wait_for_timeout(2000)

    print(
        "One-time SSO URL consumed. "
        "It will not be requested again.",
        flush=True,
    )

    print(
        f"SSO final URL: {mask_url(page.url)}",
        flush=True,
    )

    return True


def verify_servicenow_session(
    page,
    base_url: str,
):
    """
    Verify authentication using the already-created browser session.

    No SSO retry occurs here.
    """

    print("")
    print("=" * 70)
    print("Verifying ServiceNow session")
    print("=" * 70)

    response = open_page(
        page,
        base_url,
        "ServiceNow session check",
    )

    if response is None:
        print(
            "ERROR: ServiceNow instance could not be loaded.",
            flush=True,
        )
        return False

    if not response.ok:
        print(
            "ERROR: ServiceNow session check returned "
            f"HTTP {response.status}.",
            flush=True,
        )
        return False

    page.wait_for_timeout(1000)

    if looks_like_login_page(page):
        print(
            "ERROR: ServiceNow session is not authenticated.",
            flush=True,
        )

        save_debug_info(
            page,
            "session_not_authenticated",
        )

        return False

    if not same_instance(page.url, base_url):
        print(
            "WARNING: session check ended on another host: "
            f"{mask_url(page.url)}",
            flush=True,
        )

    print(
        "ServiceNow session is authenticated.",
        flush=True,
    )

    return True


def start_runner(page, target_url: str):
    print("")
    print("=" * 70)
    print("Starting Scheduled ATF Client Test Runner")
    print("=" * 70)

    runner_errors = []
    runner_requests = []

    def capture_response(response):
        try:
            url_lower = response.url.lower()

            if (
                "atf" in url_lower
                or "test_runner" in url_lower
                or "automated_test" in url_lower
            ):
                runner_requests.append(
                    (
                        response.status,
                        response.request.method,
                        response.url,
                    )
                )

                print(
                    "ATF NETWORK: "
                    f"{response.status} "
                    f"{response.request.method} "
                    f"{mask_url(response.url)}",
                    flush=True,
                )

        except Exception:
            pass

    def capture_page_error(error):
        runner_errors.append(str(error))

    page.on("response", capture_response)
    page.on("pageerror", capture_page_error)

    response = open_page(
        page,
        target_url,
        "Scheduled ATF runner",
    )

    if response is None:
        print(
            "ERROR: ATF runner request failed.",
            flush=True,
        )
        return False

    if not response.ok:
        print(
            f"ERROR: ATF runner returned HTTP {response.status}.",
            flush=True,
        )
        return False

    print(
        "Waiting for ATF runner JavaScript initialization.",
        flush=True,
    )

    startup_deadline = (
        time.monotonic()
        + STARTUP_TIMEOUT_SECONDS
    )

    last_body = ""
    found_indicator = None

    positive_indicators = (
        "client test runner",
        "test runner",
        "scheduled test",
        "scheduled runner",
        "automated test framework",
        "waiting for",
        "runner",
    )

    while time.monotonic() < startup_deadline:

        if page.is_closed():
            print(
                "ERROR: runner page was closed.",
                flush=True,
            )
            return False

        if looks_like_login_page(page):
            print(
                "ERROR: runner redirected to authentication.",
                flush=True,
            )

            save_debug_info(
                page,
                "runner_login_redirect",
            )

            return False

        try:
            body = page.locator("body").inner_text(
                timeout=3000
            )
            last_body = body
        except Exception:
            body = ""

        normalized_body = body.lower()

        for indicator in positive_indicators:
            if indicator in normalized_body:
                found_indicator = indicator

                print(
                    "Runner initialization indicator found: "
                    f"{indicator!r}",
                    flush=True,
                )
                break

        if found_indicator:
            break

        page.wait_for_timeout(1000)

    if not found_indicator:
        print(
            "WARNING: no known runner text indicator "
            "was detected during startup.",
            flush=True,
        )

    if looks_like_login_page(page):
        print(
            "ERROR: runner is on an authentication page.",
            flush=True,
        )
        return False

    body_lower = last_body.lower()

    error_indicators = (
        "access denied",
        "not authorized",
        "not authorised",
        "insufficient privileges",
        "permission denied",
        "page not found",
        "authentication required",
    )

    for indicator in error_indicators:
        if indicator in body_lower:
            print(
                f"ERROR: runner page contains {indicator!r}.",
                flush=True,
            )

            save_debug_info(
                page,
                "runner_page_error",
            )

            return False

    try:
        js_ok = page.evaluate("() => true")
    except Exception as exc:
        print(
            f"ERROR: runner JavaScript check failed: {exc}",
            flush=True,
        )
        return False

    if js_ok is not True:
        return False

    print(
        f"Runner final URL: {mask_url(page.url)}",
        flush=True,
    )

    print(
        f"Runner title: {page.title()!r}",
        flush=True,
    )

    if runner_errors:
        print(
            f"WARNING: {len(runner_errors)} "
            "browser JavaScript error(s) observed.",
            flush=True,
        )

        for error in runner_errors[:10]:
            print(
                f"  JS ERROR: {error}",
                flush=True,
            )

    print(
        f"ATF-related network responses observed: "
        f"{len(runner_requests)}",
        flush=True,
    )

    save_debug_info(
        page,
        "runner_initialized",
    )

    print("")
    print("=" * 70)
    print("Scheduled ATF runner appears active")
    print("=" * 70)

    return True


def keep_runner_alive(page):
    print("")
    print("=" * 70)
    print("Scheduled ATF runner keepalive")
    print("=" * 70)

    check_number = 0

    while not shutdown_requested:

        remaining = KEEPALIVE_SECONDS

        while (
            remaining > 0
            and not shutdown_requested
        ):
            sleep_time = min(1, remaining)
            time.sleep(sleep_time)
            remaining -= sleep_time

        if shutdown_requested:
            break

        check_number += 1

        try:
            if page.is_closed():
                print(
                    "ERROR: runner page has been closed.",
                    flush=True,
                )
                return False

            current_url = page.url
            title = page.title()

            print(
                f"Keepalive #{check_number}: "
                f"url={mask_url(current_url)!r}, "
                f"title={title!r}",
                flush=True,
            )

            if looks_like_login_page(page):
                print(
                    "ERROR: runner session lost authentication.",
                    flush=True,
                )

                save_debug_info(
                    page,
                    "keepalive_authentication_lost",
                )

                return False

            if page.evaluate("() => true") is not True:
                print(
                    "ERROR: runner JavaScript is no longer responsive.",
                    flush=True,
                )
                return False

            if page.locator("body").count() == 0:
                print(
                    "ERROR: runner page has no document body.",
                    flush=True,
                )
                return False

            try:
                body = page.locator("body").inner_text(
                    timeout=3000
                )

                snippet = (
                    body[:300]
                    .replace("\r", " ")
                    .replace("\n", " ")
                )

                print(
                    f"Keepalive body: {snippet!r}",
                    flush=True,
                )

            except Exception as exc:
                print(
                    f"WARNING: could not read runner body: {exc}",
                    flush=True,
                )

        except Exception as exc:
            print(
                f"ERROR: runner keepalive failed: {exc}",
                flush=True,
            )

            save_debug_info(
                page,
                "keepalive_failure",
            )

            return False

    print(
        "Shutdown requested. Closing runner.",
        flush=True,
    )

    return True


def main():
    print("=" * 70)
    print("ServiceNow ATF Scheduled Runner")
    print("=" * 70)

    base_url = require_value(
        "SN_URL",
        read_secret("sn_url"),
    ).rstrip("/")

    login_url = require_value(
        "LOGIN_URL",
        get_login_url(),
    )

    target_url = get_target_url(
        base_url
    )

    proxy = get_proxy_config()

    print(
        f"ServiceNow URL: {base_url}",
        flush=True,
    )

    print(
        f"Runner URL: {target_url}",
        flush=True,
    )

    print(
        f"One-time SSO URL: {mask_url(login_url)}",
        flush=True,
    )

    if proxy:
        print(
            f"Proxy: {proxy['server']}",
            flush=True,
        )
    else:
        print(
            "Proxy: not configured",
            flush=True,
        )

    with sync_playwright() as playwright:

        launch_kwargs = {
            "headless": True,
            "args": [
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        }

        if proxy:
            launch_kwargs["proxy"] = proxy

        browser = playwright.chromium.launch(
            **launch_kwargs
        )

        context = browser.new_context()

        page = context.new_page()

        page.set_default_timeout(
            PAGE_TIMEOUT_MS
        )

        setup_browser_logging(page)

        try:
            # IMPORTANT:
            # LOGIN_URL is intentionally consumed exactly once.
            if not consume_one_time_sso(
                page,
                login_url,
            ):
                return 1

            # Do not use LOGIN_URL again from this point forward.
            login_url = None

            # Verify that the session/cookies created by the SSO URL
            # work against ServiceNow.
            if not verify_servicenow_session(
                page,
                base_url,
            ):
                return 1

            # Open Scheduled ATF Runner in the SAME browser context.
            if not start_runner(
                page,
                target_url,
            ):
                return 1

            if not keep_runner_alive(page):
                return 1

            return 0

        except KeyboardInterrupt:
            return 0

        except Exception as exc:
            print(
                f"ERROR: unexpected exception: {exc}",
                flush=True,
            )

            try:
                save_debug_info(
                    page,
                    "fatal_error",
                )
            except Exception:
                pass

            return 1

        finally:
            try:
                context.close()
            except Exception:
                pass

            try:
                browser.close()
            except Exception:
                pass


if __name__ == "__main__":
    signal.signal(
        signal.SIGTERM,
        _handle_shutdown,
    )

    signal.signal(
        signal.SIGINT,
        _handle_shutdown,
    )

    sys.exit(main())