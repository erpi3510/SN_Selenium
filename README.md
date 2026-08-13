# ServiceNow SSO ATF Runner

This project starts and keeps a ServiceNow Automated Test Framework (ATF) Client Test Runner active using **Playwright with headless Chromium**.

ServiceNow's ATF runner relies on browser-side JavaScript. A plain HTTP request is therefore not sufficient. This container launches a real Chromium browser in headless mode, authenticates through a one-time/signed SSO URL, opens the ATF runner in the same browser session, and keeps that session alive.

## How it works

The startup flow is:

```text
Container starts
    ↓
Chromium starts
    ↓
Optional proxy configured?
    ├── No  → direct connection
    └── Yes → use configured proxy
    ↓
LOGIN_URL is opened exactly once
    ↓
SSO establishes the authenticated ServiceNow session
    ↓
ServiceNow session is verified
    ↓
ATF Client Test Runner is opened
    ↓
Runner initialization is checked
    ↓
Browser and session are kept alive
    ↓
SIGTERM / SIGINT
    ↓
Browser shuts down cleanly
```

The `LOGIN_URL` is intentionally consumed only once. This is important when using a single-use or signed SSO token.

The same Chromium browser context is used for authentication and the ATF runner, so cookies and session state created during SSO are retained.

## Requirements

The Python dependency is:

```text
playwright
```

Chromium is installed during the Docker build using:

```bash
playwright install --with-deps chromium
```

No locally installed browser or graphical desktop environment is required.

## Required configuration

The following variables are required:

```bash
SN_URL="https://example.service-now.com"
LOGIN_URL="https://example.service-now.com/sso?token=..."
```

### `SN_URL`

Base URL of the ServiceNow instance.

Example:

```bash
SN_URL="https://example.service-now.com"
```

### `LOGIN_URL`

Signed or one-time SSO URL used to establish the authenticated ServiceNow browser session.

Example:

```bash
LOGIN_URL="https://example.service-now.com/sso?token=..."
```

The URL is requested **exactly once per container start**.

The token/query string is redacted from application logs to avoid exposing authentication credentials.

## Build

Build the image with:

```bash
docker build -t sn-sso-launcher .
```

## Docker run

Minimal example:

```bash
docker run --rm \
  -e SN_URL="https://example.service-now.com" \
  -e LOGIN_URL="https://example.service-now.com/sso?token=..." \
  sn-sso-launcher
```

For a long-running ATF runner, detached mode is usually more convenient:

```bash
docker run -d \
  --name sn-atf-runner \
  --restart unless-stopped \
  -e SN_URL="https://example.service-now.com" \
  -e LOGIN_URL="https://example.service-now.com/sso?token=..." \
  sn-sso-launcher
```

View the runner logs with:

```bash
docker logs -f sn-atf-runner
```

Stop it cleanly with:

```bash
docker stop sn-atf-runner
```

The application handles `SIGTERM` and `SIGINT` and closes the browser cleanly.

## Docker secrets

Configuration can also be supplied through Docker secrets mounted under `/run/secrets`.

Supported secrets include:

```text
/run/secrets/sn_url
/run/secrets/login_url
/run/secrets/proxy_server
/run/secrets/proxy_username
/run/secrets/proxy_password
```

Example:

```bash
printf '%s' 'https://example.service-now.com' \
  | docker secret create sn_url -

printf '%s' 'https://example.service-now.com/sso?token=...' \
  | docker secret create login_url -
```

Environment variables take precedence when both an environment variable and a corresponding secret are available.

## ATF runner mode

`RUNNER_MODE` determines which ATF runner is opened.

### Scheduled tests

This is the default:

```bash
RUNNER_MODE="scheduled"
```

It opens:

```text
/atf_test_runner.do?sysparm_nostack=true&sysparm_scheduled_tests_only=true
```

Therefore, this does not normally need to be specified explicitly:

```bash
docker run -d \
  --name sn-atf-runner \
  -e SN_URL="https://example.service-now.com" \
  -e LOGIN_URL="https://example.service-now.com/sso?token=..." \
  sn-sso-launcher
```

### All tests

To open the runner without the scheduled-only filter:

```bash
RUNNER_MODE="all"
```

This opens:

```text
/atf_test_runner.do?sysparm_nostack=true
```

Example:

```bash
docker run -d \
  --name sn-atf-runner-all \
  -e SN_URL="https://example.service-now.com" \
  -e LOGIN_URL="https://example.service-now.com/sso?token=..." \
  -e RUNNER_MODE="all" \
  sn-sso-launcher
```

## Custom runner URL

`TARGET_URL` can be used to override the generated ATF runner URL completely.

Example:

```bash
-e TARGET_URL="https://example.service-now.com/atf_test_runner.do?sysparm_nostack=true"
```

When `TARGET_URL` is set, it takes precedence over `RUNNER_MODE`.

## Proxy support

Proxy configuration is **optional**.

If `PROXY_SERVER` is not configured, Chromium connects directly.

Example without proxy:

```bash
docker run -d \
  --name sn-atf-runner \
  -e SN_URL="https://example.service-now.com" \
  -e LOGIN_URL="https://example.service-now.com/sso?token=..." \
  sn-sso-launcher
```

To route Chromium traffic through a proxy:

```bash
-e PROXY_SERVER="http://proxy.example.com:8080"
```

For a proxy requiring authentication:

```bash
-e PROXY_SERVER="http://proxy.example.com:8080"
-e PROXY_USERNAME="user"
-e PROXY_PASSWORD="password"
```

`PROXY_USERNAME` and `PROXY_PASSWORD` are optional.

The same proxy configuration is used for the complete browser session, including:

```text
SSO authentication
        ↓
ServiceNow session verification
        ↓
ATF runner
        ↓
ATF runner keepalive
```

Proxy settings can also be provided as Docker secrets:

```text
proxy_server
proxy_username
proxy_password
```

## Optional configuration

The following settings are optional:

| Variable                  |      Default | Description                                          |
| ------------------------- | -----------: | ---------------------------------------------------- |
| `RUNNER_MODE`             |  `scheduled` | Selects scheduled-only or general ATF runner         |
| `TARGET_URL`              |            — | Completely overrides the generated runner URL        |
| `PROXY_SERVER`            |            — | Proxy server used by Chromium                        |
| `PROXY_USERNAME`          |            — | Optional proxy username                              |
| `PROXY_PASSWORD`          |            — | Optional proxy password                              |
| `PAGE_TIMEOUT_MS`         |      `30000` | Browser navigation/operation timeout in milliseconds |
| `KEEPALIVE_SECONDS`       |         `60` | Interval between runner health checks                |
| `STARTUP_TIMEOUT_SECONDS` |         `20` | Maximum time to wait for runner initialization       |
| `DEBUG_DIR`               | `/app/debug` | Directory for diagnostic screenshots                 |

Example:

```bash
docker run -d \
  --name sn-atf-runner \
  --restart unless-stopped \
  -e SN_URL="https://example.service-now.com" \
  -e LOGIN_URL="https://example.service-now.com/sso?token=..." \
  -e RUNNER_MODE="scheduled" \
  -e PAGE_TIMEOUT_MS="30000" \
  -e KEEPALIVE_SECONDS="60" \
  -e STARTUP_TIMEOUT_SECONDS="20" \
  sn-sso-launcher
```

## Debug screenshots

The application saves screenshots when useful for diagnostics and during runner initialization.

The default location inside the container is:

```text
/app/debug
```

To persist these screenshots on the Docker host, mount the directory:

```bash
mkdir -p ./debug

docker run -d \
  --name sn-atf-runner \
  -e SN_URL="https://example.service-now.com" \
  -e LOGIN_URL="https://example.service-now.com/sso?token=..." \
  -v "$(pwd)/debug:/app/debug" \
  sn-sso-launcher
```

The location inside the container can be changed using:

```bash
-e DEBUG_DIR="/app/debug"
```

## Multiple runners

Each container has its own Chromium process, browser context, cookies, SSO session, and ATF runner.

Multiple independent runners can therefore be started with different tokens or runner modes.

Example:

```bash
docker run -d \
  --name sn-runner-scheduled \
  -e SN_URL="https://example.service-now.com" \
  -e LOGIN_URL="https://example.service-now.com/sso?token=TOKEN_A" \
  -e RUNNER_MODE="scheduled" \
  sn-sso-launcher

docker run -d \
  --name sn-runner-all \
  -e SN_URL="https://example.service-now.com" \
  -e LOGIN_URL="https://example.service-now.com/sso?token=TOKEN_B" \
  -e RUNNER_MODE="all" \
  sn-sso-launcher
```

No browser state is shared between these containers.

## Authentication behavior

The authentication sequence is intentionally simple:

1. Chromium is started.
2. `LOGIN_URL` is opened **once**.
3. The SSO endpoint authenticates the browser.
4. Session cookies remain in the Playwright browser context.
5. `SN_URL` is opened to verify that the session is authenticated.
6. The ATF runner is opened using the same context.
7. `LOGIN_URL` is never automatically reused.

This design is suitable for one-time or signed SSO URLs such as:

```text
https://example.service-now.com/sso?token=...
```

### Expired sessions

If the ServiceNow session later expires or the runner is redirected back to authentication, the process reports an error and exits.

It deliberately does **not** attempt to reuse `LOGIN_URL`, because the SSO token may be single-use.

If the container is restarted, provide a valid/new `LOGIN_URL` when required by the SSO implementation.

## Runner health checks

After opening the runner, the application does more than check for HTTP `200`.

It also monitors:

* redirects to authentication pages
* browser-side JavaScript execution
* ATF-related network activity
* obvious authorization/error responses
* presence of the browser document
* runner page availability
* browser/session health during keepalive
* JavaScript/page errors

The browser remains running while the container is running so that the ATF Client Test Runner stays available.

## Expected startup

A successful startup should look approximately like:

```text
======================================================================
ServiceNow ATF Scheduled Runner
======================================================================

ServiceNow URL: https://example.service-now.com
Runner URL: https://example.service-now.com/atf_test_runner.do?...
One-time SSO URL: https://example.service-now.com/sso?<redacted>
Proxy: not configured

======================================================================
One-time SSO bootstrap
======================================================================

One-time SSO URL consumed.

======================================================================
Verifying ServiceNow session
======================================================================

ServiceNow session is authenticated.

======================================================================
Starting Scheduled ATF Client Test Runner
======================================================================

Runner initialization indicator found: 'test runner'

======================================================================
Scheduled ATF runner appears active
======================================================================

======================================================================
Scheduled ATF runner keepalive
======================================================================

Keepalive #1: ...
Keepalive #2: ...
```

## Security considerations

Do not commit real SSO URLs or tokens to the repository.

Prefer runtime configuration through environment variables or Docker secrets.

The application redacts the query string of the SSO URL from its own diagnostic output. However, credentials and tokens should still be treated as secrets at the Docker/orchestration level.

For production deployments, Docker secrets or an equivalent secret-management system are preferable to hard-coding credentials in the image.

## Notes

* Chromium runs headless; no visible GUI or desktop environment is required.
* Playwright executes the JavaScript required by ServiceNow's ATF Client Test Runner.
* No HTTP Basic Authentication is used by this application.
* `LOGIN_URL` is intended for a pre-authenticated, signed, or one-time SSO URL.
* `LOGIN_URL` is consumed only once per process start.
* Authentication and the ATF runner use the same browser context.
* Proxy configuration is optional.
* Proxy authentication is optional.
* Scheduled mode is the default.
* The browser stays open instead of exiting immediately after loading the runner.
* The process handles container shutdown signals and closes Chromium cleanly.
