from playwright.sync_api import sync_playwright

def run(playwright):
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()

    # 1. Login
    page.goto("http://localhost:5000/login")
    page.fill('input[name="username"]', "testuser")
    page.fill('input[name="password"]', "password")
    page.click('input[type="submit"]')
    page.wait_for_url("http://localhost:5000/dashboard")

    # 2. Navegar para a lixeira
    page.click('button:has-text("Ferramentas")')
    page.click('a:has-text("Lixeira do AD")')
    page.wait_for_url("http://localhost:5000/recycle_bin")

    # 3. Tirar screenshot
    page.screenshot(path="jules-scratch/verification/verification.png")

    browser.close()

with sync_playwright() as playwright:
    run(playwright)
