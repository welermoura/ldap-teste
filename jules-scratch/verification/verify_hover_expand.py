from playwright.sync_api import sync_playwright, expect

def run(playwright):
    browser = playwright.chromium.launch()
    page = browser.new_page()
    try:
        page.goto("http://localhost:5173/ad-tree")

        # 1. Aguarda a árvore e o conteúdo inicial carregarem
        page.wait_for_selector(".tree-panel", timeout=15000)

        # 2. Clica na primeira OU para carregar seus membros
        first_ou_locator = page.locator(".tree-node .node-label").first
        first_ou_locator.wait_for(state='visible', timeout=10000)
        first_ou_locator.click()

        # 3. Aguarda o painel de conteúdo ser populado
        page.wait_for_selector(".content-panel .member-item", timeout=10000)

        # 4. Encontra o primeiro item arrastável (usuário, grupo ou computador)
        draggable_item_locator = page.locator(".content-panel .member-item[draggable='true']").first
        draggable_item_locator.wait_for(state='visible', timeout=5000)

        # 5. Encontra uma segunda OU para usar como alvo do hover (assumindo que há mais de uma)
        # Vamos usar a segunda OU principal, que deve estar fechada por padrão
        target_ou_locator = page.locator(".tree-node .node-label").nth(1)
        target_ou_locator.wait_for(state='visible', timeout=5000)

        # 6. Simula o arrastar e pairar
        draggable_item_locator.hover()
        page.mouse.down()
        target_ou_locator.hover()

        # 7. Aguarda a OU se expandir - verificando se o contêiner de filhos aparece
        # A classe do contêiner dos filhos é 'node-children'
        expanded_children_locator = target_ou_locator.locator("..").locator(".node-children")

        # Aumenta o timeout para dar tempo para o atraso de 500ms + renderização
        expect(expanded_children_locator).to_be_visible(timeout=2000)

        # 8. Tira a captura de tela para verificação visual
        page.screenshot(path="jules-scratch/verification/verification_hover_expand.png")

        # (Opcional) Solta o mouse para limpar o estado de arrastar
        page.mouse.up()

    except Exception as e:
        print(f"Ocorreu um erro durante a execução do script Playwright: {e}")
        # Tira uma captura de tela em caso de erro para depuração
        page.screenshot(path="jules-scratch/verification/verification_error.png")
    finally:
        browser.close()

with sync_playwright() as playwright:
    run(playwright)
