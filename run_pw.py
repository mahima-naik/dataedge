from playwright.sync_api import sync_playwright

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://dataedge.srv1003582.hstgr.cloud/login")
        
        page.fill("#email", "realestate@procucev.com")
        page.fill("#password", "realestate123")
        page.click("#btn-submit")
        
        page.wait_for_timeout(5000) # wait 5 seconds for navigation
        
        page.screenshot(path="dashboard.png")
        print("Saved screenshot to dashboard.png")
        
        try:
            role_badge = page.locator("#role-badge").inner_text(timeout=2000)
            mobile_toolbar = page.locator(".mobile-toolbar-title").inner_text(timeout=2000)
            print("=== UI Verification ===")
            print(f"Role Badge: '{role_badge}'")
            print(f"Mobile Toolbar Title: '{mobile_toolbar}'")
            print("=======================")
        except Exception as e:
            print("Error finding elements:", e)
        
        browser.close()

if __name__ == '__main__':
    run()
