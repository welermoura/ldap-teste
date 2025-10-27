
from playwright.sync_api import sync_playwright, expect
import time

def run(playwright):
    browser = playwright.chromium.launch()
    context = browser.new_context()
    page = context.new_page()

    try:
        page.goto("http://localhost:5174/ad-tree/")

        # Espera a árvore carregar e clica na primeira OU
        page.wait_for_selector(".tree-panel", timeout=10000)
        first_ou = page.locator(".tree-panel .node-label").first
        expect(first_ou).to_be_visible()
        first_ou.click()

        # Espera o painel de conteúdo carregar e clica com o botão direito no primeiro membro (usuário)
        first_member = page.locator(".member-list .member-item").first
        expect(first_member).to_be_visible(timeout=10000)
        first_member.click(button="right")

        # Clica na opção "Editar" do menu de contexto
        edit_option = page.locator(".context-menu").get_by_text("Editar")
        expect(edit_option).to_be_visible()
        edit_option.click()

        # Espera o modal de edição abrir e clica na aba "Membro De"
        expect(page.locator(".modal-content")).to_be_visible()
        member_of_tab = page.get_by_role("button", name="Membro De")
        expect(member_of_tab).to_be_visible()
        member_of_tab.click()

        # Espera o conteúdo da aba carregar (a busca de grupos)
        expect(page.get_by_placeholder("Digite para buscar um grupo...")).to_be_visible()

        time.sleep(1) # Delay para garantir a renderização

        page.screenshot(path="jules-scratch/verification/verification_member_of_tab.png")

    except Exception as e:
        print(f"Ocorreu um erro durante a verificação: {e}")
        page.screenshot(path="jules-scratch/verification/error_member_of_tab.png")
    finally:
        browser.close()

with sync_playwright() as playwright:
    run(playwright)
