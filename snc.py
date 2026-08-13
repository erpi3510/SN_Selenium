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


# ---------------------------------------------------------------------------
# Shutdown handling
# ---------------------------------------------------------------------------

def _handle_shutdown(signum, frame):
    global shutdown_requested

    print(
        f"Shutdown signal received: {signum}",
        flush=True,
    )

    shutdown_requested = True


# ---------------------------------------------------------------------------
# Secrets / configuration
# ---------------------------------------------------------------------------

def read_secret(secret_name: str):
    """
    Read a value from an environment variable or Docker secret.
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

    secret_file = os.path.join(
        SECRET_PATH,
        secret_name,
    )

    try:
        with open(
            secret_file,
            "r",
            encoding="utf-8",
        ) as handle:
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
        https://example.service-now.com/login_with_sso.do?...
    """

    return (
        os.getenv("LOGIN_URL")
        or read_secret("login_url")
        or os.getenv("SSO_URL")
        or read_secret("sso_url")
    )


def get_target_url(base_url: str):
    """
    Build the ATF runner URL.
    """

    explicit_target = os.getenv("TARGET_URL")

    if explicit_target:
        return explicit_target.strip()

    runner_mode = (
        os.getenv(
            "RUNNER_MODE",
            "scheduled",
        )
        .strip()
        .lower()
    )

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
    """
    Proxy configuration is completely optional.
    """

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


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def mask_url(url: str):
    """
    Redact query parameters so SSO tokens do not appear in logs.
    """

    if not url:
        return url

    try:
        parsed = urlparse(url)
    except Exception:
        return "<invalid-url>"

    if not parsed.query:
        return url

    return (
        f"{parsed.scheme}://"
        f"{parsed.netloc}"
        f"{parsed.path}"
        "?<redacted>"
    )


def same_instance(url: str, base_url: str):
    try:
        return (
            urlparse(url).netloc.lower()
            == urlparse(base_url).netloc.lower()
        )
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Browser logging
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Debugging
# ---------------------------------------------------------------------------

def save_debug_info(page, prefix: str):
    try:
        os.makedirs(
            DEBUG_DIR,
            exist_ok=True,
        )

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
            timeout=5000
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


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------

def open_page(
    page,
    url: str,
    label: str,
    redact_url: bool = False,
):
    shown_url = (
        mask_url(url)
        if redact_url
        else url
    )

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

    status = (
        response.status
        if response
        else "unknown"
    )

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


# ---------------------------------------------------------------------------
# Authentication detection
# ---------------------------------------------------------------------------

def looks_like_login_page(page):
    """
    Detect obvious authentication redirects.

    Important:
    generic 'sso' is intentionally NOT treated as an error because
    the legitimate one-time login URL itself may contain /sso.
    """

    try:
        current_url = page.url.lower()
    except Exception:
        return True

    url_indicators = (
        "/login.do",
        "login.microsoftonline.com",
        "signin",
        "sign-in",
        "oauth_login",
        "saml2",
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
        body = (
            page.locator("body")
            .inner_text(timeout=2000)
            .lower()
        )

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


# ---------------------------------------------------------------------------
# One-time SSO
# ---------------------------------------------------------------------------

def consume_one_time_sso(
    page,
    login_url: str,
):
    """
    Consume LOGIN_URL exactly once.

    IMPORTANT:
    - No retries.
    - No second request to LOGIN_URL.
    - No call to SN_URL afterwards for validation.
    - Existing browser cookies/session are used directly by ATF runner.
    """

    print("")
    print("=" * 70)
    print("One-time SSO bootstrap")
    print("=" * 70)

    print(
        "IMPORTANT: LOGIN_URL will be requested exactly once.",
        flush=True,
    )

    response = open_page(
        page,
        login_url,
        "One-time SSO URL",
        redact_url=True,
    )

    if response is None:
        print(
            "ERROR: one-time SSO request failed.",
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

    # Allow cookies and JavaScript-driven redirects to complete.
    # This does NOT make another request to LOGIN_URL.
    page.wait_for_timeout(2000)

    print(
        "One-time SSO URL consumed.",
        flush=True,
    )

    print(
        "LOGIN_URL will NOT be requested again.",
        flush=True,
    )

    print(
        f"SSO final URL: {mask_url(page.url)}",
        flush=True,
    )

    return True


# ---------------------------------------------------------------------------
# ATF runner
# ---------------------------------------------------------------------------

def start_runner(
    page,
    target_url: str,
    base_url: str,
):
    """
    Open ATF runner directly after SSO.

    This is intentionally the FIRST navigation after the one-time
    SSO URL.

    There is no intermediate request to SN_URL.
    """

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

    page.on(
        "response",
        capture_response,
    )

    page.on(
        "pageerror",
        capture_page_error,
    )

    print(
        "Opening ATF runner directly with the SSO session.",
        flush=True,
    )

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

        save_debug_info(
            page,
            "runner_request_failed",
        )

        return False

    if not response.ok:
        print(
            f"ERROR: ATF runner returned HTTP {response.status}.",
            flush=True,
        )

        save_debug_info(
            page,
            "runner_http_error",
        )

        return False

    # -----------------------------------------------------------------------
    # Detect authentication redirect
    # -----------------------------------------------------------------------

    page.wait_for_timeout(1000)

    if looks_like_login_page(page):
        print(
            "ERROR: ATF runner redirected to authentication.",
            flush=True,
        )

        print(
            "The one-time SSO URL was NOT retried.",
            flush=True,
        )

        save_debug_info(
            page,
            "runner_authentication_redirect",
        )

        return False

    if not same_instance(
        page.url,
        base_url,
    ):
        print(
            "WARNING: ATF runner ended on another host: "
            f"{mask_url(page.url)}",
            flush=True,
        )

    # -----------------------------------------------------------------------
    # Wait for runner initialization
    # -----------------------------------------------------------------------

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

    while (
        time.monotonic()
        < startup_deadline
    ):

        if page.is_closed():
            print(
                "ERROR: runner page was closed.",
                flush=True,
            )
            return False

        if looks_like_login_page(page):
            print(
                "ERROR: runner session redirected "
                "to authentication.",
                flush=True,
            )

            print(
                "LOGIN_URL will not be reused.",
                flush=True,
            )

            save_debug_info(
                page,
                "runner_login_redirect",
            )

            return False

        try:
            body = (
                page.locator("body")
                .inner_text(timeout=3000)
            )

            last_body = body

        except Exception:
            body = ""

        normalized_body = (
            body.lower()
        )

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

        page.wait_for_timeout(
            1000
        )

    if not found_indicator:
        print(
            "WARNING: no known runner text indicator "
            "was detected during startup.",
            flush=True,
        )

    # -----------------------------------------------------------------------
    # Check obvious page errors
    # -----------------------------------------------------------------------

    body_lower = (
        last_body.lower()
    )

    error_indicators = (
        "access denied",
        "not authorized",
        "not authorised",
        "security constraints",
        "insufficient privileges",
        "permission denied",
        "page not found",
        "authentication required",
    )

    for indicator in error_indicators:
        if indicator in body_lower:
            print(
                "ERROR: runner page contains "
                f"{indicator!r}.",
                flush=True,
            )

            save_debug_info(
                page,
                "runner_page_error",
            )

            return False

    # -----------------------------------------------------------------------
    # JavaScript check
    # -----------------------------------------------------------------------

    try:
        js_ok = page.evaluate(
            "() => true"
        )

    except Exception as exc:
        print(
            "ERROR: runner JavaScript check failed: "
            f"{exc}",
            flush=True,
        )

        save_debug_info(
            page,
            "runner_javascript_error",
        )

        return False

    if js_ok is not True:
        print(
            "ERROR: runner JavaScript is not responsive.",
            flush=True,
        )
        return False

    print("")
    print(
        f"Runner final URL: {mask_url(page.url)}",
        flush=True,
    )

    print(
        f"Runner title: {page.title()!r}",
        flush=True,
    )

    # -----------------------------------------------------------------------
    # Diagnostics
    # -----------------------------------------------------------------------

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
        "ATF-related network responses observed: "
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


# ---------------------------------------------------------------------------
# Keepalive
# ---------------------------------------------------------------------------

def keep_runner_alive(page):
    """
    Keep Chromium and the ATF runner alive.

    IMPORTANT:
    Authentication is never retried.
    LOGIN_URL is never reused.
    """

    print("")
    print("=" * 70)
    print("Scheduled ATF runner keepalive")
    print("=" * 70)

    print(
        f"Keepalive interval: {KEEPALIVE_SECONDS}s",
        flush=True,
    )

    check_number = 0

    while not shutdown_requested:

        remaining = (
            KEEPALIVE_SECONDS
        )

        while (
            remaining > 0
            and not shutdown_requested
        ):

            sleep_time = min(
                1,
                remaining,
            )

            time.sleep(
                sleep_time
            )

            remaining -= (
                sleep_time
            )

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

            current_url = (
                page.url
            )

            title = (
                page.title()
            )

            print("")
            print(
                f"Keepalive #{check_number}: "
                f"url={mask_url(current_url)!r}, "
                f"title={title!r}",
                flush=True,
            )

            # ---------------------------------------------------------------
            # Authentication loss
            # ---------------------------------------------------------------

            if looks_like_login_page(page):
                print(
                    "ERROR: ATF runner lost authentication.",
                    flush=True,
                )

                print(
                    "LOGIN_URL will NOT be reused because "
                    "it may be single-use.",
                    flush=True,
                )

                save_debug_info(
                    page,
                    "keepalive_authentication_lost",
                )

                return False

            # ---------------------------------------------------------------
            # Browser / JavaScript health
            # ---------------------------------------------------------------

            try:
                browser_alive = page.evaluate(
                    "() => true"
                )

            except Exception as exc:
                print(
                    "ERROR: JavaScript execution failed: "
                    f"{exc}",
                    flush=True,
                )
                return False

            if browser_alive is not True:
                print(
                    "ERROR: runner JavaScript "
                    "is no longer responsive.",
                    flush=True,
                )
                return False

            # ---------------------------------------------------------------
            # DOM check
            # ---------------------------------------------------------------

            body_count = (
                page.locator("body")
                .count()
            )

            if body_count == 0:
                print(
                    "ERROR: runner page has no document body.",
                    flush=True,
                )

                save_debug_info(
                    page,
                    "keepalive_missing_body",
                )

                return False

            # ---------------------------------------------------------------
            # Diagnostic body snippet
            # ---------------------------------------------------------------

            try:
                body = (
                    page.locator("body")
                    .inner_text(timeout=3000)
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
                    "WARNING: could not read runner body: "
                    f"{exc}",
                    flush=True,
                )

        except Exception as exc:
            print(
                f"ERROR: runner keepalive failed: {exc}",
                flush=True,
            )

            try:
                save_debug_info(
                    page,
                    "keepalive_failure",
                )
            except Exception:
                pass

            return False

    print("")
    print(
        "Shutdown requested. Closing runner.",
        flush=True,
    )

    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 70)
    print("ServiceNow ATF Scheduled Runner")
    print("=" * 70)

    # -----------------------------------------------------------------------
    # Configuration
    # -----------------------------------------------------------------------

    base_url = require_value(
        "SN_URL",
        read_secret("sn_url"),
    ).rstrip("/")

    login_url = require_value(
        "LOGIN_URL",
        get_login_url(),
    )

    target_url = (
        get_target_url(
            base_url
        )
    )

    proxy = (
        get_proxy_config()
    )

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

    # -----------------------------------------------------------------------
    # Playwright
    # -----------------------------------------------------------------------

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

        # IMPORTANT:
        # Authentication and ATF runner use exactly the same
        # browser context and therefore the same cookies/session.
        context = browser.new_context()

        page = context.new_page()

        page.set_default_timeout(
            PAGE_TIMEOUT_MS
        )

        setup_browser_logging(
            page
        )

        try:
            # ---------------------------------------------------------------
            # ONE-TIME SSO
            #
            # This is the ONLY place in the complete application where
            # LOGIN_URL is passed to page.goto().
            # ---------------------------------------------------------------

            if not consume_one_time_sso(
                page,
                login_url,
            ):
                return 1

            # ---------------------------------------------------------------
            # Destroy our reference immediately.
            #
            # The URL/token must never be reused.
            # ---------------------------------------------------------------

            login_url = None

            print("")
            print(
                "One-time SSO phase complete.",
                flush=True,
            )

            print(
                "No ServiceNow home-page/session-check request "
                "will be performed.",
                flush=True,
            )

            print(
                "Opening ATF runner directly.",
                flush=True,
            )

            # ---------------------------------------------------------------
            # IMPORTANT:
            #
            # DO NOT:
            #
            #     page.goto(base_url)
            #
            # DO NOT:
            #
            #     consume_one_time_sso(...)
            #
            # again.
            #
            # Directly navigate to the ATF runner using the cookies/session
            # created by the one-time SSO request.
            # ---------------------------------------------------------------

            if not start_runner(
                page,
                target_url,
                base_url,
            ):
                return 1

            # ---------------------------------------------------------------
            # Keep runner alive
            # ---------------------------------------------------------------

            if not keep_runner_alive(
                page
            ):
                return 1

            return 0

        except KeyboardInterrupt:
            print(
                "Keyboard interrupt received.",
                flush=True,
            )
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
            print(
                "Closing browser context.",
                flush=True,
            )

            try:
                context.close()
            except Exception as exc:
                print(
                    f"WARNING: could not close context: {exc}",
                    flush=True,
                )

            print(
                "Closing browser.",
                flush=True,
            )

            try:
                browser.close()
            except Exception as exc:
                print(
                    f"WARNING: could not close browser: {exc}",
                    flush=True,
                )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":

    signal.signal(
        signal.SIGTERM,
        _handle_shutdown,
    )

    signal.signal(
        signal.SIGINT,
        _handle_shutdown,
    )

    sys.exit(
        main()
    )