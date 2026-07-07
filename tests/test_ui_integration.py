import os
import re
import socket
import subprocess
import sys
import time
import unittest
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright
except Exception:  # pragma: no cover
    sync_playwright = None
    PlaywrightError = Exception


def _wait_for_http(url: str, timeout_seconds: float = 15.0) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=1.5) as response:
                if 200 <= response.status < 500:
                    return
        except (URLError, OSError):
            time.sleep(0.15)
    raise TimeoutError(f"Server did not become ready at {url}")


def _extract_lobby_code(page) -> str:
    text = page.locator("text=Lobby Code:").first.inner_text()
    match = re.search(r"(\d{4})", text)
    if not match:
        raise AssertionError(f"Could not find lobby code in: {text!r}")
    return match.group(1)


class UiIntegrationTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sync_playwright is None:
            raise unittest.SkipTest("Playwright Python package is not installed")

        cls.repo_root = Path(__file__).resolve().parents[1]
        cls.base_url = "http://127.0.0.1:5000"

        cls.server_proc = subprocess.Popen(
            [sys.executable, "app.py"],
            cwd=str(cls.repo_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )

        try:
            _wait_for_http(cls.base_url)
        except Exception:
            cls._dump_server_output()
            cls._stop_server()
            raise

    @classmethod
    def tearDownClass(cls):
        cls._stop_server()

    @classmethod
    def _dump_server_output(cls) -> None:
        if not cls.server_proc or not cls.server_proc.stdout:
            return
        try:
            output = cls.server_proc.stdout.read()
            if output:
                print("\n--- app.py output ---\n" + output)
        except Exception:
            pass

    @classmethod
    def _stop_server(cls) -> None:
        proc = getattr(cls, "server_proc", None)
        if not proc:
            return
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)

    def _new_browser(self):
        pw = sync_playwright().start()
        try:
            browser = pw.chromium.launch(headless=True)
        except PlaywrightError as exc:
            pw.stop()
            raise unittest.SkipTest(f"Chromium browser is unavailable: {exc}")
        return pw, browser

    def test_lobby_role_assignment_and_start_flow(self):
        pw, browser = self._new_browser()
        try:
            host = browser.new_page()
            friend_a = browser.new_page()
            friend_b = browser.new_page()

            host.goto(self.base_url)
            host.click("#go-create")
            host.fill("#create-username", "host_01")
            host.click("#create-submit")
            host.wait_for_selector("text=Lobby Code:")
            code = _extract_lobby_code(host)

            friend_a.goto(self.base_url)
            friend_a.click("#go-join")
            friend_a.fill("#join-code", code)
            friend_a.fill("#join-username", "alice")
            friend_a.click("#join-submit")
            friend_a.wait_for_selector("text=Lobby Code:")

            friend_b.goto(self.base_url)
            friend_b.click("#go-join")
            friend_b.fill("#join-code", code)
            friend_b.fill("#join-username", "bob")
            friend_b.click("#join-submit")
            friend_b.wait_for_selector("text=Lobby Code:")

            host.wait_for_selector("text=Players: 3")

            # Start is blocked before BRIDE/GROOM are set.
            self.assertTrue(host.is_disabled("#start-game"))

            host.select_option('select.role-select[data-user="alice"]', "BRIDE")
            host.select_option('select.role-select[data-user="bob"]', "GROOM")

            host.wait_for_timeout(250)
            self.assertFalse(host.is_disabled("#start-game"))

            host.fill("#questions-box", "first question")
            host.click("#start-game")

            host.wait_for_selector("text=Impersonate!")
            friend_a.wait_for_selector("text=Impersonate!")
            friend_b.wait_for_selector("text=Impersonate!")
        finally:
            browser.close()
            pw.stop()

    def test_voting_reveal_shows_centered_answer_blocks(self):
        pw, browser = self._new_browser()
        try:
            host = browser.new_page()
            friend_a = browser.new_page()
            friend_b = browser.new_page()

            host.goto(self.base_url)
            host.click("#go-create")
            host.fill("#create-username", "host_01")
            host.click("#create-submit")
            code = _extract_lobby_code(host)

            friend_a.goto(self.base_url)
            friend_a.click("#go-join")
            friend_a.fill("#join-code", code)
            friend_a.fill("#join-username", "alice")
            friend_a.click("#join-submit")

            friend_b.goto(self.base_url)
            friend_b.click("#go-join")
            friend_b.fill("#join-code", code)
            friend_b.fill("#join-username", "bob")
            friend_b.click("#join-submit")

            host.wait_for_selector("text=Players: 3")
            host.select_option('select.role-select[data-user="alice"]', "BRIDE")
            host.select_option('select.role-select[data-user="bob"]', "GROOM")
            host.fill("#questions-box", "who is the funniest")
            host.click("#start-game")

            host.wait_for_selector("#answer-box")
            friend_a.wait_for_selector("#answer-box")
            friend_b.wait_for_selector("#answer-box")

            host.fill("#answer-box", "answer one")
            host.click("#answer-submit")
            friend_a.fill("#answer-box", "answer two")
            friend_a.click("#answer-submit")
            friend_b.fill("#answer-box", "answer three")
            friend_b.click("#answer-submit")

            host.wait_for_selector("#start-voting:not([disabled])")
            host.click("#start-voting")

            host.wait_for_selector("text=Vote Now")
            friend_a.wait_for_selector("text=Vote Now")
            friend_b.wait_for_selector("text=Vote Now")

            host.locator("button.answer-btn:not([disabled])").first.click()
            friend_a.locator("button.answer-btn:not([disabled])").first.click()
            friend_b.locator("button.answer-btn:not([disabled])").first.click()

            host.wait_for_selector("#reveal-first:not([disabled])")
            host.click("#reveal-first")
            host.wait_for_selector("#host-reveal-votes")
            host.click("#host-reveal-votes")

            host.wait_for_selector(".reveal-authors")
            host.wait_for_selector(".reveal-answer")
            host.wait_for_selector(".reveal-votes")

            # Ensure reveal content exists and is centered via class presence.
            self.assertTrue(host.locator(".reveal-authors").count() > 0)
            self.assertTrue(host.locator(".reveal-answer").count() > 0)
            self.assertTrue(host.locator(".reveal-votes").count() > 0)
        finally:
            browser.close()
            pw.stop()


if __name__ == "__main__":
    unittest.main()
