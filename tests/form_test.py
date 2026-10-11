#!/usr/bin/env python3
"""End-to-end test of the AI Agent blueprint form (Playwright, Chrome channel, 390x844 phone emulation).

Serves the project folder on localhost, types Thai, presses ส่งเข้า LINE and intercepts the line.me
navigation (answered with 204 so the page stays put), then asserts the exact URL and decoded text.
No request ever leaves localhost: line.me is intercepted, anything else non-local fails the test.

    python3 tests/form_test.py                 # assertions only
    python3 tests/form_test.py --shots DIR     # also write screenshots to DIR
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import functools
import http.server
import socket
import sys
import threading
from pathlib import Path
from urllib.parse import quote, unquote

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
URL_LIMIT = 1999
LINE_BASE = "https://line.me/R/oaMessage/%40pngoung/?"
FRIEND_URL = "https://line.me/R/ti/p/%40pngoung"
PHONE = {"viewport": {"width": 390, "height": 844}, "device_scale_factor": 3, "is_mobile": True,
         "has_touch": True, "locale": "th-TH"}

BUSINESS_TYPED = "ร้านวัสดุก่อสร้าง ขายส่งให้ผู้รับเหมา"
ANSWER_TYPED = "ตามใบเสนอราคาที่ลูกค้ายังไม่ตอบ\nแล้วสรุปให้ฉันทุกเช้า   ว่าควรโทรหาใครก่อน"
ANSWER_NORMALIZED = "ตามใบเสนอราคาที่ลูกค้ายังไม่ตอบ แล้วสรุปให้ฉันทุกเช้า ว่าควรโทรหาใครก่อน"


def expected_text(business: str, answer: str, campaign: str = "IESA6") -> str:
    return (f"#AIAGENT {campaign}\nธุรกิจ: {business}\nอยากให้ผู้ช่วย AI ทำก่อน: {answer}\n"
            "(ขอรับไอเดียการวางระบบ AI Agent ภายใน 24 ชม.)")


def encode_component(text: str) -> str:
    """Python twin of JS encodeURIComponent (unreserved: A-Z a-z 0-9 - _ . ! ~ * ' ( ))."""
    return quote(text, safe="!~*'()")


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args) -> None:  # keep test output readable
        pass


@contextlib.contextmanager
def serve(root: Path):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), functools.partial(QuietHandler, directory=str(root)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()


class Results:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[str] = []

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        (self.passed if ok else self.failed).append(name + ("" if ok else f" :: {detail}"))
        print(("  PASS " if ok else "  FAIL ") + name + ("" if ok else f" :: {detail}"), flush=True)


async def open_page(browser, base: str, query: str, log: dict, size: dict | None = None):
    ctx = await browser.new_context(**{**PHONE, **({"viewport": size} if size else {})})
    page = await ctx.new_page()
    log.setdefault("line", [])
    log.setdefault("foreign", [])
    log.setdefault("errors", [])

    async def on_line(route):
        log["line"].append(route.request.url)
        await route.fulfill(status=204, body="")

    await page.route("https://line.me/**", on_line)
    page.on("request", lambda r: log["foreign"].append(r.url)
            if not (r.url.startswith(base) or r.url.startswith("https://line.me/") or r.url.startswith("data:")) else None)
    page.on("pageerror", lambda e: log["errors"].append(f"pageerror: {e}"))
    page.on("console", lambda m: log["errors"].append(f"console.{m.type}: {m.text}") if m.type in ("error", "warning") else None)
    await page.goto(f"{base}/{query}")
    await page.evaluate("() => document.fonts.ready.then(() => true)")
    return ctx, page


async def wait_for_line(log: dict, count: int, timeout: float = 5.0) -> None:
    for _ in range(int(timeout / 0.05)):
        if len(log["line"]) >= count:
            return
        await asyncio.sleep(0.05)


async def shot(page, shots: Path | None, name: str, full: bool = False) -> None:
    if shots:
        await asyncio.sleep(0.6)  # let the entrance motion settle
        await page.screenshot(path=str(shots / f"{name}.png"), full_page=full)
        print(f"  shot {name}.png", flush=True)


async def run(shots: Path | None) -> Results:
    res = Results()
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(channel="chrome")
        with serve(ROOT) as base:
            # 1. first impression + config
            log: dict = {}
            ctx, page = await open_page(browser, base, "?c=IESA6", log)
            res.check("kicker from config", await page.locator(".kicker").inner_text() == "IESA S-Curve MBA รุ่น 6 · โค้ชง้วง")
            res.check("counters start at 0/160 and 0/300",
                      await page.locator("#business-count").inner_text() == "0/160"
                      and await page.locator("#answer-count").inner_text() == "0/300")
            res.check("add-friend link", await page.locator("#friend-link").get_attribute("href") == FRIEND_URL)
            res.check("labels bound to fields",
                      await page.get_by_label("ธุรกิจของคุณ").count() == 1
                      and await page.get_by_label("ถ้ามีผู้ช่วยเพิ่มหนึ่งคน ฉันอยากมอบหมายให้เขา…").count() == 1)
            tap = await page.locator("button[type=submit]").bounding_box()
            res.check("primary button tap target >= 48px", tap and tap["height"] >= 48, str(tap))
            no_hscroll = await page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth")
            res.check("no horizontal scroll at 390", no_hscroll)
            await shot(page, shots, "01-form-390")

            # 2. empty submit -> Thai errors, no navigation
            await page.locator("button[type=submit]").click()
            res.check("empty submit shows business error",
                      await page.locator("#business-error").inner_text() == "กรุณาใส่ธุรกิจของคุณ")
            res.check("empty submit shows answer error",
                      await page.locator("#answer-error").inner_text() == "กรุณาเขียนงานที่อยากมอบหมายให้ผู้ช่วย")
            res.check("aria-invalid set", await page.locator("#business").get_attribute("aria-invalid") == "true")
            res.check("focus moves to first invalid field", await page.evaluate("() => document.activeElement.id") == "business")
            await asyncio.sleep(0.3)
            res.check("empty submit does not open LINE", not log["line"])
            await shot(page, shots, "02-errors-390")

            # 3. type Thai, Enter in business moves on, submit -> exact URL
            await page.locator("#business").press_sequentially(BUSINESS_TYPED, delay=8)
            await page.locator("#business").press("Enter")
            res.check("Enter in business moves to answer", await page.evaluate("() => document.activeElement.id") == "answer")
            res.check("Enter in business does not submit", not log["line"])
            res.check("business error clears while typing", await page.locator("#business-error").is_hidden())
            await page.locator("#answer").fill(ANSWER_TYPED)
            res.check("business counter counts", await page.locator("#business-count").inner_text() == f"{len(BUSINESS_TYPED)}/160")
            res.check("answer counter counts", await page.locator("#answer-count").inner_text() == f"{len(ANSWER_TYPED)}/300")
            await shot(page, shots, "03-filled-390")
            await page.locator("button[type=submit]").click()
            await wait_for_line(log, 1)
            text = expected_text(BUSINESS_TYPED, ANSWER_NORMALIZED)
            want = LINE_BASE + encode_component(text)
            got = log["line"][0] if log["line"] else ""
            res.check("submit opens exact line.me oaMessage URL", got == want, f"\n got={got}\nwant={want}")
            res.check("decoded text is the exact 4-line message", unquote(got.split("/?", 1)[-1]) == text,
                      repr(unquote(got.split('/?', 1)[-1])))
            res.check("URL under 2,000 chars", 0 < len(got) < 2000, str(len(got)))
            res.check("sent state visible", await page.locator("#done-view").is_visible())
            res.check("sent state copy", "เปิด LINE แล้ว กด ส่ง ได้เลย" in await page.locator("#done-title").inner_text())
            res.check("preview shows the message", await page.locator("#preview").inner_text() == text)
            res.check("ส่งอีกครั้ง re-opens the same URL", await page.locator("#resend-link").get_attribute("href") == want)
            await shot(page, shots, "04-sent-390", full=True)
            await page.locator("#resend-link").click()
            await wait_for_line(log, 2)
            res.check("ส่งอีกครั้ง navigates to the same URL", len(log["line"]) >= 2 and log["line"][1] == want)
            await page.locator("#edit-button").click()
            res.check("แก้ไขคำตอบ returns to the form with values kept",
                      await page.locator("#form-view").is_visible()
                      and await page.locator("#business").input_value() == BUSINESS_TYPED)
            res.check("no requests left localhost", not log["foreign"], str(log["foreign"]))
            res.check("no console errors", not log["errors"], str(log["errors"]))
            await ctx.close()

            # 4. maxlength + URL budget guard (300 Thai chars cannot fit a 2,000-char link)
            log = {}
            ctx, page = await open_page(browser, base, "?c=IESA6", log)
            await page.locator("#business").focus()
            await page.keyboard.insert_text("ก" * 200)
            res.check("business maxlength 160 enforced", len(await page.locator("#business").input_value()) == 160)
            await page.locator("#business").fill("โรงงานผลิตชิ้นส่วนรถยนต์")
            await page.locator("#answer").focus()
            await page.keyboard.insert_text("ข" * 400)
            answer_value = await page.locator("#answer").input_value()
            res.check("answer maxlength 300 enforced", len(answer_value) == 300, str(len(answer_value)))
            budget = await page.locator("#budget").inner_text()
            res.check("over-budget message shown", budget.startswith("ข้อความยาวเกินที่ LINE รับได้ · ลดอีก "), budget)
            cut = int("".join(ch for ch in budget if ch.isdigit()) or 0)
            fit = lambda n: len(LINE_BASE + encode_component(expected_text("โรงงานผลิตชิ้นส่วนรถยนต์", "ข" * (300 - n)))) <= URL_LIMIT
            res.check("cut count is exact (fits after N, not after N-1)", fit(cut) and not fit(cut - 1), str(cut))
            await page.locator("button[type=submit]").click()
            await asyncio.sleep(0.3)
            res.check("over-budget submit is blocked", not log["line"])
            res.check("over-budget submit focuses answer", await page.evaluate("() => document.activeElement.id") == "answer")
            await shot(page, shots, "05-over-budget-390")
            await page.locator("#answer").fill("ข" * (300 - cut))
            await page.locator("button[type=submit]").click()
            await wait_for_line(log, 1)
            res.check("longest allowed message opens LINE under 2,000", log["line"] and len(log["line"][0]) <= URL_LIMIT,
                      str(len(log["line"][0]) if log["line"] else None))
            await ctx.close()

            # 5. campaign selection: case-insensitive id, unknown id falls back to the default
            for query, label in (("?c=iesa6", "lowercase id"), ("?c=NOPE", "unknown id"), ("", "no id")):
                log = {}
                ctx, page = await open_page(browser, base, query, log)
                await page.locator("#business").fill("คลินิกความงาม")
                await page.locator("#answer").fill("ตอบคำถามราคาซ้ำ ๆ")
                await page.locator("button[type=submit]").click()
                await wait_for_line(log, 1)
                want = LINE_BASE + encode_component(expected_text("คลินิกความงาม", "ตอบคำถามราคาซ้ำ ๆ"))
                res.check(f"campaign {label} -> IESA6 message", log["line"][:1] == [want], str(log["line"][:1]))
                await ctx.close()

            # 6. extreme widths
            for size, name in (({"width": 360, "height": 740}, "06-form-360"), ({"width": 430, "height": 932}, "07-form-430")):
                log = {}
                ctx, page = await open_page(browser, base, "?c=IESA6", log, size)
                res.check(f"no horizontal scroll at {size['width']}",
                          await page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth"))
                await shot(page, shots, name)
                if size["width"] == 360:
                    await page.locator("#business").fill(BUSINESS_TYPED)
                    await page.locator("#answer").fill(ANSWER_TYPED)
                    await page.locator("button[type=submit]").click()
                    await wait_for_line(log, 1)
                    await shot(page, shots, "08-sent-360", full=True)
                await ctx.close()
        await browser.close()
    return res


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shots", type=Path, default=None)
    args = parser.parse_args()
    if args.shots:
        args.shots.mkdir(parents=True, exist_ok=True)
    res = asyncio.run(run(args.shots))
    print(f"\n{len(res.passed)} passed, {len(res.failed)} failed")
    for item in res.failed:
        print("  FAILED:", item)
    return 1 if res.failed else 0


if __name__ == "__main__":
    sys.exit(main())
