/**
 * ShineHub toast notifications.
 * showToast() is a small global utility every future AJAX flow
 * (bookings, payments, notifications) can call — this is the one
 * place toast markup and timing lives.
 */
(function () {
  const ICONS = {
    success: 'fa-circle-check',
    error: 'fa-circle-exclamation',
    warning: 'fa-triangle-exclamation',
    info: 'fa-circle-info',
    debug: 'fa-circle-info',
  };

  const ACCENTS = {
    success: 'border-l-4 border-l-green-500',
    error: 'border-l-4 border-l-brandpink',
    warning: 'border-l-4 border-l-amber-500',
    info: 'border-l-4 border-l-brandblue',
    debug: 'border-l-4 border-l-slate-400',
  };

  function showToast(text, tag) {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const level = ACCENTS[tag] ? tag : 'info';
    const toast = document.createElement('div');
    toast.className = `toast ${ACCENTS[level]} px-4 py-3 flex items-start gap-3 animate-[fadeIn_0.2s_ease]`;
    toast.setAttribute('role', 'status');
    toast.innerHTML = `
      <i class="fa-solid ${ICONS[level]} mt-0.5 text-ink"></i>
      <p class="text-sm text-ink flex-1">${text}</p>
      <button type="button" aria-label="Dismiss notification" class="text-ink-soft hover:text-ink">
        <i class="fa-solid fa-xmark"></i>
      </button>
    `;
    toast.querySelector('button').addEventListener('click', () => toast.remove());
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 6000);
  }

  window.showToast = showToast;

  document.addEventListener('DOMContentLoaded', () => {
    const serverMessages = document.querySelectorAll('#server-messages [data-text]');
    serverMessages.forEach((el) => {
      showToast(el.getAttribute('data-text'), el.getAttribute('data-tag'));
    });
  });
})();
