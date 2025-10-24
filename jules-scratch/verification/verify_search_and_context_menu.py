
from playwright.sync_api import sync_playwright, expect
import time

def run(playwright):
    browser = playwright.chromium.launch()
    context = browser.new_context()
    page = context.new_page()

    try:
        # 1. Acessar a página
        page.goto("http://localhost:5175/ad-tree/")

        # 2. Esperar o painel da árvore carregar e encontrar a primeira OU
        page.wait_for_selector(".tree-panel", timeout=10000)
        first_ou = page.locator(".tree-panel .node-label").first
        expect(first_ou).to_be_visible()

        # 3. Clicar na primeira OU para carregar seus membros
        first_ou.click()

        # 4. Esperar que os membros apareçam no painel de conteúdo
        # Aumentamos o timeout aqui para dar tempo à API de responder
        first_member = page.locator(".member-list .member-item").first
        expect(first_member).to_be_visible(timeout=10000)

        # 5. Clicar com o botão direito no primeiro membro para abrir o menu
        first_member.click(button="right")

        # 6. Verificar se o menu de contexto está visível
        context_menu = page.locator(".context-menu")
        expect(context_menu).to_be_visible()

        # 7. Adicionar um pequeno delay para garantir que a renderização CSS (hover) seja capturada
        time.sleep(0.5)

        # 8. Tirar a captura de tela
        page.screenshot(path="jules-scratch/verification/verification.png")

    except Exception as e:
        print(f"Ocorreu um erro durante a verificação: {e}")
        page.screenshot(path="jules-scratch/verification/error.png") # Salva screenshot em caso de erro
    finally:
        browser.close()

with sync_playwright() as playwright:
    run(playwright)
