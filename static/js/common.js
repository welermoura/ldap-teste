// Funções JavaScript comuns

/**
 * Exibe uma notificação toast.
 * @param {string} message - A mensagem a ser exibida.
 * @param {string} [type='info'] - O tipo de toast ('info', 'success', 'error').
 * @param {string} [title='Notificação'] - O título do toast.
 */
function showToast(message, type = 'info', title = 'Notificação') {
    const toastContainer = document.getElementById('toast-container');
    if (!toastContainer) {
        console.error('Toast container not found!');
        return;
    }

    const toastId = 'toast-' + Date.now();
    const title_color = (type === 'error') ? 'text-danger' : (type === 'success') ? 'text-success' : 'text-primary';

    const toastHTML = `
        <div id="${toastId}" class="toast" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="toast-header">
                <strong class="me-auto ${title_color}">${title}</strong>
                <button type="button" class="btn-close" data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
            <div class="toast-body">
                ${message}
            </div>
        </div>`;

    toastContainer.insertAdjacentHTML('beforeend', toastHTML);

    const toastElement = document.getElementById(toastId);
    const toast = new bootstrap.Toast(toastElement);
    toast.show();

    toastElement.addEventListener('hidden.bs.toast', () => {
        toastElement.remove();
    });
}


// --- Funções para Modal de Confirmação Genérico ---

let currentConfirmAction = () => {};

/**
 * Configura e exibe um modal de confirmação genérico.
 * @param {string} title - O título do modal.
 * @param {string} body - O texto do corpo do modal.
 * @param {function} onConfirmCallback - A função a ser executada ao confirmar.
 */
function setupConfirmationModal(title, body, onConfirmCallback) {
    const confirmationModalEl = document.getElementById('confirmationModal');
    if (!confirmationModalEl) {
        console.error('Confirmation modal element not found!');
        return;
    }
    const confirmationModal = bootstrap.Modal.getOrCreateInstance(confirmationModalEl);
    const modalLabel = document.getElementById('confirmationModalLabel');
    const modalBody = document.getElementById('confirmationModalBody');

    if(modalLabel) modalLabel.textContent = title;
    if(modalBody) modalBody.textContent = body;

    currentConfirmAction = onConfirmCallback;
    confirmationModal.show();
}

/**
 * Lida com o cancelamento de uma ausência agendada.
 * @param {string} username - O nome de usuário.
 * @param {string} csrfToken - O token CSRF.
 * @param {function} [callback] - Função opcional a ser chamada após o sucesso.
 */
async function handleCancelAbsence(username, csrfToken, callback) {
    setupConfirmationModal(
        'Confirmar Cancelamento',
        `Tem certeza que deseja cancelar o agendamento de ausência para ${username}? A conta será reativada imediatamente se o período de ausência já tiver começado.`,
        async () => {
            try {
                const response = await fetch(`/api/cancel_absence/${username}`, {
                    method: 'POST',
                    headers: { 'X-CSRFToken': csrfToken, 'Content-Type': 'application/json' }
                });
                const result = await response.json();
                if (!response.ok) {
                    throw new Error(result.error || 'Erro desconhecido');
                }
                showToast('Agendamento cancelado com sucesso!', 'success', 'Sucesso');

                if (typeof callback === 'function') {
                    callback();
                }
            } catch (error) {
                showToast(`Falha ao cancelar agendamento: ${error.message}`, 'error', 'Erro');
                console.error('Erro ao cancelar agendamento:', error);
            }
        }
    );
}

document.addEventListener('DOMContentLoaded', function() {
    const confirmActionBtn = document.getElementById('confirmActionBtn');
    if (confirmActionBtn) {
        confirmActionBtn.addEventListener('click', function() {
            if (typeof currentConfirmAction === 'function') {
                currentConfirmAction();
            }
            const confirmationModalEl = document.getElementById('confirmationModal');
            const confirmationModal = bootstrap.Modal.getInstance(confirmationModalEl);
            if (confirmationModal) {
                confirmationModal.hide();
            }
        });
    }
});
