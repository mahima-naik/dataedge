import asyncio
import sys
from playwright.async_api import async_playwright

async def verify_page():
    print("Launching playwright with fake media devices...")
    errors = []
    
    async with async_playwright() as p:
        # Launch headless browser with fake media stream flags
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--use-fake-ui-for-media-stream",
                "--use-fake-device-for-media-stream"
            ]
        )
        context = await browser.new_context(
            permissions=["microphone"] # grant mic permissions
        )
        page = await context.new_page()
        
        # Listen for console errors
        page.on("pageerror", lambda err: errors.append(f"Page Error: {err.message}"))
        page.on("console", lambda msg: errors.append(f"Console {msg.type}: {msg.text}") if msg.type == "error" else None)
        
        url = "http://localhost:8000/voice_test.html?role=sellers"
        print(f"Navigating to {url}...")
        
        await page.goto(url, wait_until="networkidle")
        
        # Verify page title and header
        title = await page.title()
        print(f"Page Title: {title}")
        
        role_lbl = await page.locator("#role-label").inner_text()
        print(f"Role label: {role_lbl}")
        
        if role_lbl != "sellers":
            print("Error: Role label doesn't match 'sellers'")
            sys.exit(1)
            
        # Click start button
        print("Clicking start button to connect voice...")
        await page.click("#start-btn")
        
        # Wait a few seconds to let WebSocket connect and stream some audio
        await asyncio.sleep(5)
        
        # Check if the status updated to live/connected
        status = await page.locator("#status").inner_text()
        print(f"Status after start click: {status}")
        
        # Click stop button
        print("Clicking stop button...")
        await page.click("#stop-btn")
        await asyncio.sleep(2)
        
        await browser.close()
        
    if errors:
        print("\n=== ERRORS DETECTED ===")
        for err in errors:
            print(err)
        print("=======================")
        sys.exit(1)
    else:
        print("\nNo console/page errors detected during page load and WebSocket run.")
        print("Verification successful!")

if __name__ == "__main__":
    asyncio.run(verify_page())
