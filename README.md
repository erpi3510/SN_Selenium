# ServiceNow SSO URL Launcher

This project logs in and opens the ATF runner using headless Chromium via
Playwright. ServiceNow's UI requires JavaScript execution to actually start
the test runner, so a plain HTTP request is not enough - Playwright runs a
real (but headless, no visible window) browser to handle that.

## Recommended flow

Use a single signed SSO URL that is valid for 24 hours.

Example:

```bash
export SN_URL="https://example.service-now.com"
export LOGIN_URL="https://example.service-now.com/sso?token=..."
```

Or via Docker secrets mounted to `/run/secrets`:

```bash
printf '%s' 'https://example.service-now.com' | docker secret create sn_url -
printf '%s' 'https://example.service-now.com/sso?token=...' | docker secret create login_url -
```

## Docker run

```bash
docker build -t sn-sso-launcher .
docker run --rm \
  -e SN_URL="https://example.service-now.com" \
  -e LOGIN_URL="https://example.service-now.com/sso?token=..." \
  sn-sso-launcher
```

## Fallback behavior

If no login URL is provided, the script loads the ServiceNow runner URL directly:

```bash
docker run --rm \
  -e SN_URL="https://example.service-now.com" \
  sn-sso-launcher
```

## Login then runner

If `LOGIN_URL` is set, the script loads it first in the headless browser (so
any JavaScript-driven SSO redirect completes), then navigates to the runner
URL in the same browser context (session cookies carry over). Real HTTP
status codes and errors are printed for each navigation instead of being
swallowed silently. A screenshot is saved on unexpected errors.

```bash
-e PAGE_TIMEOUT_MS=30000
```

## Runner mode (scheduled vs. all tests)

`RUNNER_MODE` controls which ATF runner URL is used by default:

- `scheduled` (default): `/atf_test_runner.do?sysparm_nostack=true&sysparm_scheduled_tests_only=true`
- `all`: `/atf_test_runner.do?sysparm_nostack=true` (no scheduled-only filter)

```bash
-e RUNNER_MODE=all
```

Set `TARGET_URL` instead if you need a fully custom URL - it always wins
over `RUNNER_MODE`.

## Multiple containers with different tokens/modes

Each container is fully independent - just run several with different
`LOGIN_URL` and `RUNNER_MODE`/`TARGET_URL` values, no shared state needed:

```bash
docker run -d --name sn-runner-scheduled \
  -e SN_URL="https://example.service-now.com" \
  -e LOGIN_URL="https://example.service-now.com/sso?token=TOKEN_A" \
  -e RUNNER_MODE=scheduled \
  sn-sso-launcher

docker run -d --name sn-runner-all \
  -e SN_URL="https://example.service-now.com" \
  -e LOGIN_URL="https://example.service-now.com/sso?token=TOKEN_B" \
  -e RUNNER_MODE=all \
  sn-sso-launcher
```

## Proxy

Set `PROXY_SERVER` (and optionally `PROXY_USERNAME`/`PROXY_PASSWORD`) to
route the browser traffic through a proxy. Works as env vars or Docker secrets
(`proxy_server`, `proxy_username`, `proxy_password`).

```bash
-e PROXY_SERVER="http://myproxy.example.com:3128"
-e PROXY_USERNAME="user"
-e PROXY_PASSWORD="pass"
```

## Notes

- No Basic Auth is used.
- No visible GUI/window is used - Chromium runs headless inside the container.
- Playwright's Chromium executes the page's JavaScript, which ServiceNow's ATF runner requires.
- This is intended for a pre-authenticated SSO link or a signed login URL from ServiceNow or your IdP.
- The script runs once per container start and exits.
