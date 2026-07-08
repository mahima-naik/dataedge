#!/usr/bin/env python3
"""Screenshot the live DataEdge site to verify red theme."""
import asyncio
from playwright.async_api import async_playwright
from pathlib import Path

OUTPUT = Path("/Users/surya/Desktop/Data-Edge/theme_screenshots/live_red_verification.png")

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        await page.goto("https://dataedge.srv1003582.hstgr.cloud/", wait_until="networkidle")
        await asyncio.sleep(1)
        await page.screenshot(path=str(OUTPUT), full_page=False)
        print(f"Saved: {OUTPUT}")
        await browser.close()

asyncio.run(main())
