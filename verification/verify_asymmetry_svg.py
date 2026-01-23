from playwright.sync_api import sync_playwright
import time

def verify_asymmetry_svg():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_viewport_size({"width": 1600, "height": 900})

        print("Navigating...")
        page.goto("http://localhost:5001/organograma")
        page.wait_for_selector(".org-tree", timeout=10000)
        time.sleep(1)

        # 1. Expand "Huge Branch" to create asymmetry
        print("Expanding Huge Branch...")
        page.get_by_text("Huge Branch").click()
        time.sleep(1) # Wait for expansion

        # 2. Hover "Leaf One" (Far Left)
        print("Hovering Leaf One...")
        page.get_by_text("Leaf One").hover()
        time.sleep(1)
        page.screenshot(path="/home/jules/verification/asymmetry_svg_leaf1.png")

        browser.close()

if __name__ == "__main__":
    verify_asymmetry_svg()
