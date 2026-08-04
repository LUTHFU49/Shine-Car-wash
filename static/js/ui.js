/**
 * ShineHub site chrome behaviors: scroll-reveal for `.reveal` elements
 * and the public-site mobile nav toggle.
 *
 * (Formerly theme.js — the dark/light theme toggle that used to live
 * here has been removed; ShineHub now ships a single light theme.)
 */
(function () {
  document.addEventListener('DOMContentLoaded', () => {
    // Scroll-reveal for elements marked with class "reveal"
    const revealEls = document.querySelectorAll('.reveal');
    if ('IntersectionObserver' in window && revealEls.length) {
      const observer = new IntersectionObserver(
        (entries) => {
          entries.forEach((entry) => {
            if (entry.isIntersecting) {
              entry.target.classList.add('in-view');
              observer.unobserve(entry.target);
            }
          });
        },
        { threshold: 0.15 }
      );
      revealEls.forEach((el) => observer.observe(el));
    } else {
      revealEls.forEach((el) => el.classList.add('in-view'));
    }

    // Mobile nav toggle (public site navbar)
    const mobileToggle = document.querySelector('[data-mobile-nav-toggle]');
    const mobileMenu = document.querySelector('[data-mobile-nav-menu]');
    if (mobileToggle && mobileMenu) {
      mobileToggle.addEventListener('click', () => {
        const isOpen = !mobileMenu.classList.contains('hidden');
        mobileMenu.classList.toggle('hidden');
        mobileToggle.setAttribute('aria-expanded', String(!isOpen));
      });
    }
  });
})();
