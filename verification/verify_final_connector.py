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

        # 2. Wait for tree to render (CEO)
        print("Waiting for CEO...")
        page.wait_for_selector('[id="CN=CEO"]')

        # 3. Expand Huge Branch to reveal aggregate group
        print("Expanding Huge Branch...")
        page.click('[id="CN=HugeBranch"]')
        time.sleep(1)

        # 4. Hover over Sub 1 to activate path
        print("Hovering Sub 1...")
        page.hover('[id="CN=Sub1"]')
        time.sleep(1)

        # Capture screenshot of the connection to the aggregate box
        page.screenshot(path="final_aggregate_check.png")
        print("Captured final_aggregate_check.png")

        browser.close()

if __name__ == "__main__":
    run()
