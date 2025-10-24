from playwright.sync_api import sync_playwright

def run(playwright):
    browser = playwright.chromium.launch()
    page = browser.new_page()
    try:
        page.goto("http://localhost:5173/ad-tree")

        # Aguarda o painel da árvore estar visível
        page.wait_for_selector(".tree-panel", timeout=15000)

        # Encontra um nó de OU (vamos pegar o primeiro que encontrar)
        # Usamos um seletor que busca um elemento com a classe 'node-label' dentro de 'tree-node'
        ou_node_locator = page.locator(".tree-node .node-label").first

        # Espera o nó ser visível
        ou_node_locator.wait_for(state='visible', timeout=10000)

        # Clica no nó para expandi-lo e carregar os membros
        ou_node_locator.click()

        # Aguarda o painel de conteúdo ser atualizado e exibir a lista de membros
        page.wait_for_selector(".content-panel .member-list", timeout=10000)

        # Tira a captura de tela da página inteira para ver a árvore e o conteúdo
        page.screenshot(path="jules-scratch/verification/verification.png")

    except Exception as e:
        print(f"Ocorreu um erro durante a execução do script Playwright: {e}")
    finally:
        browser.close()

with sync_playwright() as playwright:
    run(playwright)
