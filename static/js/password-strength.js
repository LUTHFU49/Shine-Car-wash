(function () {
  function scorePassword(value) {
    let score = 0;
    if (value.length >= 8) score += 1;
    if (value.length >= 12) score += 1;
    if (/[A-Z]/.test(value)) score += 1;
    if (/[a-z]/.test(value)) score += 1;
    if (/[0-9]/.test(value)) score += 1;
    if (/[^A-Za-z0-9]/.test(value)) score += 1;
    return score; // 0-6
  }

  const LEVELS = [
    { max: 1, color: '#DC2626', label: 'Very weak' },
    { max: 2, color: '#F59E0B', label: 'Weak' },
    { max: 4, color: '#0013DE', label: 'Good' },
    { max: 6, color: '#16A34A', label: 'Strong' },
  ];

  function levelFor(score) {
    return LEVELS.find((l) => score <= l.max) || LEVELS[LEVELS.length - 1];
  }

  document.addEventListener('DOMContentLoaded', () => {
    const input = document.querySelector('[data-password-strength]');
    const meter = document.querySelector('[data-password-strength-meter]');
    if (!input || !meter) return;

    const bar = meter.querySelector('[data-strength-bar]');
    const label = meter.querySelector('[data-strength-label]');

    input.addEventListener('input', () => {
      const value = input.value;
      if (!value) {
        bar.style.width = '0%';
        label.textContent = 'Use 8+ characters with upper, lower, number & symbol.';
        return;
      }
      const score = scorePassword(value);
      const level = levelFor(score);
      bar.style.width = `${Math.min(100, (score / 6) * 100)}%`;
      bar.style.backgroundColor = level.color;
      label.textContent = level.label;
      label.style.color = level.color;
    });
  });
})();
