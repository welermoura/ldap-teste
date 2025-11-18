// Funções JavaScript comuns

/**
 * Exibe uma notificação toast.
 * @param {string} [title='Notificação'] - O título do toast.
 * @param {string} message - A mensagem a ser exibida.
 * @param {string} [type='info'] - O tipo de toast ('info', 'success', 'error').
 */
function showToast(title = 'Notificação', message, type = 'info') {
    const toastContainer = document.getElementById('toast-container');
    if (!toastContainer) {
        console.error('Toast container not found!');
        return;
    }

    const toastId = 'toast-' + Date.now();
    // Define a cor do texto com base no tipo para o cabeçalho
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

    // Remove o elemento da DOM depois que o toast é escondido
    toastElement.addEventListener('hidden.bs.toast', () => {
        toastElement.remove();
    });
}
