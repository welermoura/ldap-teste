
from playwright.sync_api import sync_playwright, expect
import time

def run(playwright):
    browser = playwright.chromium.launch()
    context = browser.new_context()
    page = context.new_page()

    try:
        # 1. Acessar a página
        page.goto("http://localhost:5173/ad-tree/")

        # 2. Esperar o painel da árvore carregar e encontrar o nó da lixeira
        page.wait_for_selector(".tree-panel", timeout=10000)
        recycle_bin_node = page.locator(".recycle-bin-container .node-label")
        expect(recycle_bin_node).to_be_visible()

        # 3. Clicar no nó da lixeira
        recycle_bin_node.click()

        # 4. Verificar se o painel de conteúdo mostra o cabeçalho da lixeira
        content_header = page.get_by_role("heading", name="Lixeira")
        expect(content_header).to_be_visible(timeout=5000)

        # 5. Adicionar um pequeno delay para garantir renderização completa
        time.sleep(1)

        # 6. Tirar a captura de tela
        page.screenshot(path="jules-scratch/verification/verification_recycle_bin.png")

    except Exception as e:
        print(f"Ocorreu um erro durante a verificação da lixeira: {e}")
        page.screenshot(path="jules-scratch/verification/error_recycle_bin.png")
    finally:
        browser.close()

with sync_playwright() as playwright:
    run(playwright)
