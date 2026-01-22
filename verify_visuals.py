from playwright.sync_api import sync_playwright
import time

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        try:
            page.goto("http://localhost:5001/organograma")
            print("Page loaded.")

            page.wait_for_selector(".org-card")
            print("Root node found.")

            # Find the CEO node
            ceo_card = page.locator(".org-card").first

            # Hover
            print("Hovering...")
            ceo_card.hover()

            # Wait longer
            time.sleep(3)

            # Check
            tooltip = page.locator(".node-tooltip")
            if tooltip.is_visible():
                print("SUCCESS: Tooltip is visible.")
                print(f"Content: {tooltip.text_content()}")
            else:
                print("FAILURE: Tooltip hidden.")
                # Debug: check if any event listeners are active? Hard.

            page.screenshot(path="tooltip_retry.png")

        except Exception as e:
            print(f"Error: {e}")

        browser.close()

if __name__ == "__main__":
    run()
