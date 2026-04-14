let _toastTimeout = null;

document.addEventListener('DOMContentLoaded', function () {
    const toast = document.getElementById('toast');
    if (toast) {
        const ms = parseInt(toast.dataset.timeout || '3000', 10);
        toast.style.setProperty('--toast-duration', ms + 'ms');
    }
});

function showToast(message, status = 'success') {
    const toast = document.getElementById('toast');
    if (!toast) return;
    toast.textContent = message;
    toast.classList.remove('success', 'error', 'visible', 'flash-auto');
    toast.classList.add(status);
    requestAnimationFrame(() => toast.classList.add('visible'));
    if (_toastTimeout) clearTimeout(_toastTimeout);
    const timeout = parseInt(toast.dataset.timeout);
    _toastTimeout = setTimeout(() => toast.classList.remove('visible'), timeout);
}
