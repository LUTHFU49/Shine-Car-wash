/**
 * Toggles the mobile sidebar overlay in the internal app shell
 * (templates/layouts/app_base.html). Separate from ui.js's
 * public-site mobile nav toggle, which targets different elements.
 */
(function () {
  document.addEventListener('DOMContentLoaded', () => {
    const toggle = document.querySelector('[data-mobile-sidebar-toggle]');
    const panel = document.querySelector('[data-mobile-sidebar-panel]');
    const backdrop = document.querySelector('[data-mobile-sidebar-backdrop]');
    if (!toggle || !panel) return;

    const open = () => panel.classList.remove('hidden');
    const close = () => panel.classList.add('hidden');

    toggle.addEventListener('click', open);
    if (backdrop) backdrop.addEventListener('click', close);
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') close();
    });
  });
})();
