
from playwright.sync_api import sync_playwright, expect
import time

def run(playwright):
    browser = playwright.chromium.launch()
    context = browser.new_context()
    page = context.new_page()

    try:
        # 1. Acessar a página
        page.goto("http://localhost:5173/ad-tree/")

        # 2. Esperar o painel da árvore carregar
        page.wait_for_selector(".tree-panel", timeout=10000)

        # 3. Esperar que pelo menos um nó da árvore esteja visível
        expect(page.locator(".tree-panel .node-label").first).to_be_visible(timeout=10000)

        # 4. Adicionar um pequeno delay para garantir renderização completa
        time.sleep(1)

        # 5. Tirar a captura de tela
        page.screenshot(path="jules-scratch/verification/verification_containers.png")

    except Exception as e:
        print(f"Ocorreu um erro durante a verificação: {e}")
        page.screenshot(path="jules-scratch/verification/error_containers.png")
    finally:
        browser.close()

with sync_playwright() as playwright:
    run(playwright)
