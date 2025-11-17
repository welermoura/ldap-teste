// Funções JavaScript comuns

/**
 * Exibe uma notificação toast de forma flexível.
 * Esta função pode ser chamada com 1, 2 ou 3 argumentos para se adaptar a diferentes usos.
 * - showToast(message): Título e tipo padrão.
 * - showToast(message, type): Título padrão, mensagem e tipo especificados.
 * - showToast(title, message, type): Título, mensagem e tipo especificados.
 */
function showToast(arg1, arg2, arg3) {
    let title, message, type;
    const validTypes = ['info', 'success', 'error', 'warning'];

    // Lógica para lidar com a sobrecarga de argumentos
    if (arg3 !== undefined && validTypes.includes(arg3)) {
        // Chamada com 3 argumentos: showToast('Título', 'Mensagem', 'success')
        title = arg1;
        message = arg2;
        type = arg3;
    } else if (arg2 !== undefined) {
        // Chamada com 2 argumentos
        if (validTypes.includes(arg2)) {
            // showToast('Mensagem', 'error')
            message = arg1;
            type = arg2;
            title = type.charAt(0).toUpperCase() + type.slice(1);
        } else {
            // showToast('Título', 'Mensagem') - tipo padrão 'info'
            title = arg1;
            message = arg2;
            type = 'info';
        }
    } else {
        // Chamada com 1 argumento: showToast('Mensagem')
        message = arg1;
        type = 'info';
        title = 'Notificação';
    }

    // Garante que o tipo tenha um valor padrão se for nulo ou indefinido
    type = type || 'info';

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
