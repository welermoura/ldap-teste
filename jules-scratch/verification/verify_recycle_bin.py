from playwright.sync_api import sync_playwright

def run(playwright):
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()

    # 1. Login
    page.goto("http://localhost:5000/login")
    page.fill('input[name="username"]', "testuser")
    page.fill('input[name="password"]', "password")
    page.click('input[type="submit"]')
    page.wait_for_url("http://localhost:5000/dashboard")

    # 2. Navegar para a árvore do AD
    page.goto("http://localhost:5000/ad-tree")

    # 3. Clicar no nó da lixeira
    # Usamos um seletor que encontra o nó da árvore pelo texto "Lixeira"
    page.click('span.node-text:has-text("Lixeira")')

    # 4. Aguardar a atualização do painel de conteúdo
    # (Adicione uma espera explícita se a chamada de API for lenta)
    page.wait_for_timeout(2000) # Espera 2 segundos para a API carregar

    # 5. Tirar screenshot
    page.screenshot(path="jules-scratch/verification/verification.png")

    browser.close()

with sync_playwright() as playwright:
    run(playwright)
