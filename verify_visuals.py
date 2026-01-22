from playwright.sync_api import sync_playwright
import time

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        try:
            page.goto("http://localhost:5001/organograma")
            print("Page loaded.")

            # Wait for data load
            page.wait_for_selector(".org-card")

            # Simulate Search
            # We want to find "Subordinate Fifteen". It is > 12, so normally hidden.
            # In the real app, "OrganogramSearch" component handles this.
            # We can simulate the effect by programmatically focusing the node via console or if we can trigger the search input.

            # Let's try to type in the search input if it exists
            search_input = page.locator("input[placeholder='Buscar...']")
            if search_input.count() > 0:
                print("Search input found. Typing...")
                search_input.fill("Fifteen")
                time.sleep(1)
                page.keyboard.press("ArrowDown")
                page.keyboard.press("Enter")
                time.sleep(2)

                # Check if "Subordinate Fifteen" is visible
                target = page.get_by_text("Subordinate Fifteen")
                if target.is_visible():
                    print("SUCCESS: Hidden target found and visible.")
                else:
                    print("FAILURE: Target not visible.")
            else:
                # Fallback: manually expand parent and check if it auto-expands?
                # No, the requirement is about auto-expanding when *focused*.
                # If we can't use search, we can't easily test "focus" from outside without search component working.
                print("Search input not found or implemented in mock?")

            page.screenshot(path="search_verification.png", full_page=True)

        except Exception as e:
            print(f"Error: {e}")

        browser.close()

if __name__ == "__main__":
    run()
