from playwright.sync_api import sync_playwright
import time

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        # 1. Load the page (Mock Server on 5001)
        print("Navigating to http://localhost:5001/organograma")
        page.goto("http://localhost:5001/organograma")

        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except:
            print("Network idle timeout, continuing...")

        # 2. Wait for tree to render
        print("Waiting for node...")
        page.wait_for_selector('[id="CN=Leaf1"]')

        # 3. Hover over Leaf One (Left side)
        print("Hovering Leaf One...")
        page.hover('[id="CN=Leaf1"]')
        time.sleep(1) # Wait for animation/render

        # Screenshot
        page.screenshot(path="asymmetry_svg_leaf1_fixed.png")
        print("Captured asymmetry_svg_leaf1_fixed.png")

        # 4. Hover over Huge Branch (Aggregate)
        print("Hovering Huge Branch...")
        page.hover('[id="CN=HugeBranch"]')
        time.sleep(1)
        page.screenshot(path="asymmetry_svg_huge_branch.png")
        print("Captured asymmetry_svg_huge_branch.png")

        browser.close()

if __name__ == "__main__":
    run()
