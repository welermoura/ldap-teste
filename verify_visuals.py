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

            # Based on mock_data, we need to navigate deep to find a leaf group > 8
            # The mock data has "Director Big Team" -> 10 children (leaves).
            # So expanding Director should show the aggregate box if implemented correctly.

            # Expand CEO
            ceo_locator = page.get_by_text("Chief Executive")
            if ceo_locator.count() > 0:
                 ceo_locator.click()
                 time.sleep(1)

            # Expand Director
            director_locator = page.get_by_text("Director Big Team")
            if director_locator.count() > 0:
                print("Director found. Expanding...")
                director_locator.click()
                time.sleep(2)

                # Check for Aggregate Box
                if page.locator(".aggregate-box").count() > 0:
                    print("SUCCESS: Aggregate Box found.")
                    header_text = page.locator(".aggregate-header h5").inner_text()
                    print(f"Header: {header_text}")
                else:
                    print("FAILURE: Aggregate Box NOT found. Grid wrapper might be present.")
                    if page.locator(".org-grid-wrapper").count() > 0:
                        print("Found org-grid-wrapper instead.")

            page.screenshot(path="aggregate_verification.png", full_page=True)
            print("Screenshot saved to aggregate_verification.png")

        except Exception as e:
            print(f"Error: {e}")

        browser.close()

if __name__ == "__main__":
    run()
