#!/usr/bin/env python3
"""
Captures full-page screenshots at desktop (1440x900), tablet (768x1024), and mobile (390x844),
in light and dark theme, across 9 interface states:
1. empty_state
2. streaming_answer
3. expanded_work_details
4. citation_hover_card
5. artifact_panel_open
6. memory_overlay
7. settings_overlay
8. history_drawer
9. command_palette

Saves all captures to docs/ui/screenshots/ and records console errors / hydration warnings.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from playwright.async_api import async_playwright

ROOT_DIR = Path(__file__).resolve().parent.parent
SCREENSHOT_DIR = ROOT_DIR / "docs" / "ui" / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

VIEWPORTS = {
    "desktop": {"width": 1440, "height": 900},
    "tablet": {"width": 768, "height": 1024},
    "mobile": {"width": 390, "height": 844},
}

THEMES = ["dark", "light"]


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        
        console_errors = []
        network_failures = []

        print(f"[*] Starting screenshot capture into {SCREENSHOT_DIR}...")

        for vp_name, vp_size in VIEWPORTS.items():
            for theme in THEMES:
                context = await browser.new_context(
                    viewport=vp_size,
                    color_scheme="dark" if theme == "dark" else "light",
                )
                page = await context.new_page()

                def handle_console(msg):
                    if msg.type in ("error", "warning"):
                        console_errors.append(f"[{vp_name}_{theme}] Console {msg.type}: {msg.text}")

                def handle_req_fail(req):
                    network_failures.append(f"[{vp_name}_{theme}] Failed request: {req.url} ({req.failure})")

                page.on("console", handle_console)
                page.on("requestfailed", handle_req_fail)

                # Set theme helper
                async def apply_theme():
                    if theme == "light":
                        await page.evaluate("""() => {
                            document.documentElement.classList.remove('dark');
                            document.documentElement.classList.add('light');
                        }""")
                    else:
                        await page.evaluate("""() => {
                            document.documentElement.classList.remove('light');
                            document.documentElement.classList.add('dark');
                        }""")

                # 1. Empty State
                await page.goto("http://127.0.0.1:3000", wait_until="networkidle")
                await apply_theme()
                await page.wait_for_timeout(300)
                await page.screenshot(
                    path=str(SCREENSHOT_DIR / f"{vp_name}_{theme}_empty_state.png"),
                    full_page=True,
                )
                print(f"Captured: {vp_name}_{theme}_empty_state.png")

                # 2. History Drawer
                history_btn = page.locator('button[aria-label="History"], button:has-text("History"), [title="History"]').first
                if await history_btn.count() > 0:
                    await history_btn.click()
                else:
                    # Click history toggle icon in header
                    await page.click('button:has(svg.lucide-history)')
                await page.wait_for_timeout(300)
                await page.screenshot(
                    path=str(SCREENSHOT_DIR / f"{vp_name}_{theme}_history_drawer.png"),
                    full_page=True,
                )
                print(f"Captured: {vp_name}_{theme}_history_drawer.png")
                await page.keyboard.press("Escape")
                await page.wait_for_timeout(200)

                # 3. Command Palette (Ctrl+K / Cmd+K)
                await page.keyboard.press("Control+k")
                await page.wait_for_timeout(300)
                await page.screenshot(
                    path=str(SCREENSHOT_DIR / f"{vp_name}_{theme}_command_palette.png"),
                    full_page=True,
                )
                print(f"Captured: {vp_name}_{theme}_command_palette.png")
                await page.keyboard.press("Escape")
                await page.wait_for_timeout(200)

                # 4. Settings Overlay
                await page.goto("http://127.0.0.1:3000/?overlay=settings", wait_until="networkidle")
                await apply_theme()
                await page.wait_for_timeout(300)
                await page.screenshot(
                    path=str(SCREENSHOT_DIR / f"{vp_name}_{theme}_settings_overlay.png"),
                    full_page=True,
                )
                print(f"Captured: {vp_name}_{theme}_settings_overlay.png")

                # 5. Memory Overlay
                await page.goto("http://127.0.0.1:3000/?overlay=memory", wait_until="networkidle")
                await apply_theme()
                await page.wait_for_timeout(400)
                await page.screenshot(
                    path=str(SCREENSHOT_DIR / f"{vp_name}_{theme}_memory_overlay.png"),
                    full_page=True,
                )
                print(f"Captured: {vp_name}_{theme}_memory_overlay.png")

                # 6. Streaming Answer & Work Status Line
                await page.goto("http://127.0.0.1:3000", wait_until="networkidle")
                await apply_theme()
                
                # Type query in composer textarea
                textarea = page.locator("textarea").first
                await textarea.fill("research the latest breakthroughs in solid-state batteries")
                await page.keyboard.press("Enter")
                
                # Capture while streaming
                await page.wait_for_timeout(200)
                await page.screenshot(
                    path=str(SCREENSHOT_DIR / f"{vp_name}_{theme}_streaming_answer.png"),
                    full_page=True,
                )
                print(f"Captured: {vp_name}_{theme}_streaming_answer.png")

                # Wait for stream to complete
                await page.wait_for_timeout(1800)

                # 7. Expanded Work Details
                # Click on the live status line accordion to reveal details
                status_line = page.locator("button:has-text('Parallel retrieval completed'), button:has-text('Decomposing research query'), div[role='button']").first
                if await status_line.count() > 0:
                    await status_line.click()
                    await page.wait_for_timeout(300)
                await page.screenshot(
                    path=str(SCREENSHOT_DIR / f"{vp_name}_{theme}_expanded_work_details.png"),
                    full_page=True,
                )
                print(f"Captured: {vp_name}_{theme}_expanded_work_details.png")

                # 8. Citation Hover Card / Sources Sheet
                # Find citation chip button
                cit_btn = page.locator("button:has(svg.lucide-external-link), button:has-text('[')").first
                if await cit_btn.count() > 0:
                    await cit_btn.hover()
                    await page.wait_for_timeout(200)
                    await cit_btn.click()
                    await page.wait_for_timeout(300)
                await page.screenshot(
                    path=str(SCREENSHOT_DIR / f"{vp_name}_{theme}_citation_hover_card.png"),
                    full_page=True,
                )
                print(f"Captured: {vp_name}_{theme}_citation_hover_card.png")
                await page.keyboard.press("Escape")
                await page.wait_for_timeout(200)

                # 9. Artifact Panel Open
                art_card = page.locator("button:has-text('Deep Research Synthesis Report'), button:has(svg.lucide-file-text)").first
                if await art_card.count() > 0:
                    await art_card.click()
                    await page.wait_for_timeout(300)
                await page.screenshot(
                    path=str(SCREENSHOT_DIR / f"{vp_name}_{theme}_artifact_panel_open.png"),
                    full_page=True,
                )
                print(f"Captured: {vp_name}_{theme}_artifact_panel_open.png")

                await context.close()

        await browser.close()

        print("\n=======================================================")
        print(f" SCREENSHOT CAPTURE COMPLETE: 54 screenshots generated")
        print(f" Location: {SCREENSHOT_DIR}")
        print(f" Console errors encountered: {len(console_errors)}")
        for err in console_errors:
            print("  -", err)
        print(f" Failed network requests: {len(network_failures)}")
        for fail in network_failures:
            print("  -", fail)
        print("=======================================================\n")


if __name__ == "__main__":
    asyncio.run(main())
