from playwright.sync_api import sync_playwright

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://dataedge.srv1003582.hstgr.cloud/login")
        
        # Wait for the email input
        page.wait_for_selector("input[type='email']")
        page.fill("input[type='email']", "realestate@procucev.com")
        page.fill("input[type='password']", "realestate123")
        page.click("button[type='submit']")
        
        # Wait for navigation or a specific element indicating login success
        page.wait_for_timeout(5000)
        
        page.screenshot(path="/Users/surya/Desktop/Data-Edge/snapshot.png")
        
        html = page.content()
        with open("/Users/surya/Desktop/Data-Edge/page.html", "w") as f:
            f.write(html)
        
        # Also let's extract some text to verify
        body_text = page.locator("body").inner_text()
        with open("/Users/surya/Desktop/Data-Edge/body_text.txt", "w") as f:
            f.write(body_text)
            
        browser.close()

if __name__ == '__main__':
    run()
