"""Manual LinkedIn OAuth flow test via Playwright (+ optional API diagnostic).

Usage (from repo root):
  set CONTENT_ENGINE_EMAIL=you@example.com
  set CONTENT_ENGINE_PASSWORD=your-password
  python scripts/test_linkedin_oauth.py

  # OAuth URL only (no browser):
  python scripts/test_linkedin_oauth.py --api-only

Env:
  CONTENT_ENGINE_URL  default https://contentengine.generalming.me
  HEADLESS            default 0 (headed — complete LinkedIn login in the window)
  MANUAL_WAIT_MS      default 180000
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
import time
from urllib.parse import parse_qs, urlparse

import httpx
from playwright.async_api import Page, async_playwright, TimeoutError as PlaywrightTimeout

BASE_URL = os.environ.get("CONTENT_ENGINE_URL", "https://contentengine.generalming.me").rstrip("/")
CE_EMAIL = os.environ.get("CONTENT_ENGINE_EMAIL", "").strip()
CE_PASSWORD = os.environ.get("CONTENT_ENGINE_PASSWORD", "").strip()
LI_EMAIL = os.environ.get("LINKEDIN_EMAIL", "").strip()
LI_PASSWORD = os.environ.get("LINKEDIN_PASSWORD", "").strip()
HEADLESS = os.environ.get("HEADLESS", "0") == "1"
PROFILE_DIR = os.path.join(os.path.dirname(__file__), ".playwright-linkedin-profile")
SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "linkedin_oauth_screenshots")
MANUAL_WAIT_MS = int(os.environ.get("MANUAL_WAIT_MS", "180000"))


def _log(msg: str) -> None:
    print(msg, flush=True)


def _parse_oauth_url(url: str) -> dict[str, str]:
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    return {k: v[0] if v else "" for k, v in qs.items()}


async def diagnose_oauth_url_api() -> int:
    """Login via API and print the LinkedIn authorize URL params (no browser)."""
    if not CE_EMAIL or not CE_PASSWORD:
        _log("Set CONTENT_ENGINE_EMAIL and CONTENT_ENGINE_PASSWORD to run --api-only.")
        return 1

    _log(f"API diagnostic against {BASE_URL}")
    async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
        login_resp = await client.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": CE_EMAIL, "password": CE_PASSWORD},
        )
        if login_resp.status_code != 200:
            _log(f"Login failed ({login_resp.status_code}): {login_resp.text[:300]}")
            return 1

        token = login_resp.json()["access_token"]
        user = login_resp.json().get("user", {})
        _log(f"Logged in as {user.get('email')} (verified={user.get('email_verified')})")

        app_resp = await client.get(
            f"{BASE_URL}/api/credentials/linkedin/app",
            headers={"Authorization": f"Bearer {token}"},
        )
        if app_resp.status_code == 200:
            app = app_resp.json()
            _log(f"LinkedIn app configured: {app.get('configured')} (source={app.get('source')})")
            _log(f"  redirect_uri (Settings): {app.get('redirect_uri')}")

        oauth_resp = await client.get(
            f"{BASE_URL}/api/publish/linkedin/oauth-url",
            headers={"Authorization": f"Bearer {token}"},
        )
        if oauth_resp.status_code != 200:
            _log(f"oauth-url failed ({oauth_resp.status_code}): {oauth_resp.text[:400]}")
            return 1

        data = oauth_resp.json()
        url = data["url"]
        params = _parse_oauth_url(url)
        expected = f"{BASE_URL}/api/publish/linkedin/callback"

        _log("\n=== OAuth authorize URL (from API) ===")
        _log(f"  client_id:     {params.get('client_id', '(missing)')}")
        _log(f"  redirect_uri:  {params.get('redirect_uri', '(missing)')}")
        _log(f"  scope:         {params.get('scope', '(missing)')}")
        _log(f"  response_type: {params.get('response_type', '(missing)')}")
        _log(f"\n  Register client_id above in LinkedIn Developer Portal → Auth → redirect URLs:")
        _log(f"  {expected}")

        if params.get("redirect_uri") != expected:
            _log("\nMISMATCH: redirect_uri in OAuth URL != expected production callback.")
            return 1

        _log("\nOK: redirect_uri matches. Register it on the app with this client_id.")
        _log(f"\nFull authorize URL:\n{url}")
        return 0


async def _screenshot(page: Page, name: str) -> None:
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    path = os.path.join(SCREENSHOT_DIR, f"{name}.png")
    await page.screenshot(path=path, full_page=True)
    _log(f"  screenshot: {path}")


async def _login_content_engine(page: Page) -> None:
    await page.goto(f"{BASE_URL}/login", wait_until="domcontentloaded", timeout=60_000)
    await _screenshot(page, "01_login_page")

    if CE_EMAIL and CE_PASSWORD:
        await page.get_by_label(re.compile(r"email", re.I)).fill(CE_EMAIL)
        await page.get_by_label(re.compile(r"password", re.I)).fill(CE_PASSWORD)
        await page.get_by_role("button", name=re.compile(r"sign in", re.I)).click()
        try:
            await page.wait_for_url(re.compile(r".*/(dashboard|settings|library).*"), timeout=30_000)
        except PlaywrightTimeout:
            pass
    else:
        _log(f"No CE credentials — log in manually in the browser ({MANUAL_WAIT_MS // 1000}s max)...")
        try:
            await page.wait_for_url(
                re.compile(r".*/(dashboard|settings|library|verify).*"),
                timeout=MANUAL_WAIT_MS,
            )
        except PlaywrightTimeout:
            _log("Timed out waiting for Content Engine login.")
            raise

    await _screenshot(page, "02_logged_in")


async def _try_linkedin_login(page: Page) -> None:
    if LI_EMAIL and LI_PASSWORD:
        try:
            await page.wait_for_selector('input[name="session_key"], #username', timeout=15_000)
            await page.fill('input[name="session_key"], #username', LI_EMAIL)
            await page.fill('input[name="session_password"], #password', LI_PASSWORD)
            await page.click('button[type="submit"]')
            await page.wait_for_load_state("networkidle", timeout=30_000)
            return
        except PlaywrightTimeout:
            _log("  LinkedIn login form not found — may already be signed in.")

    _log(f"Complete LinkedIn authorize/login in the browser ({MANUAL_WAIT_MS // 1000}s max)...")
    deadline = time.monotonic() + MANUAL_WAIT_MS / 1000
    while time.monotonic() < deadline:
        url = page.url
        if "contentengine.generalming.me" in url:
            break
        if "linkedin.com/oauth" in url and "login" not in url:
            # Consent screen — wait for user to click Allow
            pass
        await asyncio.sleep(1)
    await page.wait_for_load_state("domcontentloaded", timeout=30_000)


async def run() -> int:
    _log(f"Testing LinkedIn OAuth at {BASE_URL}")
    _log(f"Headless={HEADLESS}")

    async with async_playwright() as p:
        os.makedirs(PROFILE_DIR, exist_ok=True)
        context = await p.chromium.launch_persistent_context(
            PROFILE_DIR,
            headless=HEADLESS,
            ignore_https_errors=True,
            viewport={"width": 1280, "height": 900},
        )
        page = context.pages[0] if context.pages else await context.new_page()

        try:
            await _login_content_engine(page)

            await page.goto(f"{BASE_URL}/settings", wait_until="domcontentloaded", timeout=60_000)
            await _screenshot(page, "03_settings")

            connect = page.get_by_role("button", name=re.compile(r"Connect LinkedIn", re.I))
            if await connect.count() == 0:
                _log("ERROR: Connect LinkedIn button not found.")
                _log(f"  Current URL: {page.url}")
                await _screenshot(page, "error_no_connect_button")
                return 1

            if not await connect.first.is_enabled():
                _log("ERROR: Connect LinkedIn is disabled — save app credentials first.")
                await _screenshot(page, "error_connect_disabled")
                return 1

            async with page.expect_navigation(timeout=60_000, wait_until="domcontentloaded"):
                await connect.first.click()

            await _screenshot(page, "04_after_connect_click")

            if "linkedin.com" not in page.url:
                _log(f"ERROR: Expected redirect to linkedin.com, got: {page.url}")
                return 1

            params = _parse_oauth_url(page.url)
            _log("\n=== LinkedIn OAuth authorize URL ===")
            _log(f"  client_id:    {params.get('client_id', '(missing)')}")
            _log(f"  redirect_uri: {params.get('redirect_uri', '(missing)')}")
            _log(f"  scope:        {params.get('scope', '(missing)')}")
            _log(f"  response_type:{params.get('response_type', '(missing)')}")
            _log(f"  full URL:     {page.url[:200]}...")

            expected_redirect = f"{BASE_URL}/api/publish/linkedin/callback"
            actual_redirect = params.get("redirect_uri", "")
            if actual_redirect != expected_redirect:
                _log(f"\nMISMATCH: redirect_uri should be {expected_redirect}")
            else:
                _log("\nOK: redirect_uri matches production callback.")

            await _try_linkedin_login(page)
            await _screenshot(page, "05_after_linkedin_auth")

            final_url = page.url
            _log(f"\n=== Final URL ===\n  {final_url}")

            if "contentengine.generalming.me/settings" in final_url:
                if "linkedin=connected" in final_url:
                    _log("\nSUCCESS: OAuth completed — LinkedIn connected.")
                    return 0
                if "linkedin=error" in final_url or "linkedin=denied" in final_url:
                    _log("\nFAIL: Returned to settings with OAuth error.")
                    return 1
                _log("\nPARTIAL: Back on settings but no linkedin=connected param.")
                return 1

            if "linkedin.com/feed" in final_url or final_url.rstrip("/").endswith("linkedin.com"):
                _log("\nFAIL: Landed on LinkedIn feed — OAuth callback never fired.")
                _log("  Likely causes: client_id mismatch, app not in Development testers, missing products.")
                return 1

            if "/api/publish/linkedin/callback" in final_url:
                _log("\nPARTIAL: Hit callback URL — waiting for redirect to settings...")
                await page.wait_for_url(re.compile(r".*/settings.*"), timeout=30_000)
                await _screenshot(page, "06_callback_redirect")
                if "linkedin=connected" in page.url:
                    _log("SUCCESS: Callback redirected to settings with connected status.")
                    return 0
                _log(f"FAIL: Callback redirected to {page.url}")
                return 1

            _log("\nUNKNOWN: Unexpected final destination.")
            return 1

        finally:
            await context.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test LinkedIn OAuth flow")
    parser.add_argument("--api-only", action="store_true", help="Login via API and print OAuth URL only")
    args = parser.parse_args()
    try:
        if args.api_only:
            raise SystemExit(asyncio.run(diagnose_oauth_url_api()))
        raise SystemExit(asyncio.run(run()))
    except KeyboardInterrupt:
        raise SystemExit(130) from None
