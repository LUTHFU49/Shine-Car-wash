/**
 * ShineHub global real-time validation library.
 * -----------------------------------------------------------------
 * Auto-attaches to every input/select/textarea inside every <form>
 * on the page — no per-template wiring required. It classifies each
 * field (phone, email, name, numeric, date, password, plate, search,
 * textarea-with-counter, generic) from its existing `type`, `name`,
 * `pattern`, and `autocomplete` attributes — the same attributes the
 * Django forms already render — and adds:
 *
 *   - live validation as the user types / pastes / blurs
 *   - blocking of clearly-invalid keystrokes where practical
 *   - inline success/error messaging with icons
 *   - a green/pink border state
 *   - a submit-time loading state on the form's submit button
 *
 * IMPORTANT: this is a client-side UX layer only. The server-side
 * validators (apps/*/forms.py, apps/*/validators.py) remain the
 * final authority — every <form novalidate> still posts to Django
 * and Django still re-validates everything.
 * -----------------------------------------------------------------
 */
(function () {
  'use strict';

  // Mirrors apps/accounts/models.py's phone_validator: optional
  // leading +, 9-15 digits.
  const PHONE_RE = /^\+?[0-9]{9,15}$/;
  // Mirrors apps/customers/forms.py / apps/accounts/forms.py NAME_REGEX.
  const NAME_RE = /^[A-Za-z][A-Za-z\s\-']*$/;
  // Mirrors apps/core/validators.py KENYA_PLATE_PATTERN (spaces/dashes stripped first).
  const PLATE_RE = /^K[A-Z]{2}\d{3}[A-Z]$/;
  const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  // Mirrors apps/accounts/validators.py ComplexPasswordValidator.
  const PW_SPECIAL_RE = /[!@#$%^&*(),.?":{}|<>_\-\[\]\\/+=~`]/;

  function debounce(fn, wait) {
    let t;
    return function (...args) {
      clearTimeout(t);
      t = setTimeout(() => fn.apply(this, args), wait);
    };
  }

  /* ------------------------------------------------------------
     Classify a field into a validator "kind" using attributes
     that are already present on the rendered widget.
     ------------------------------------------------------------ */
  function classify(el, form) {
    const name = (el.getAttribute('name') || '').toLowerCase();
    const id = (el.id || '').toLowerCase();
    const type = (el.getAttribute('type') || (el.tagName === 'TEXTAREA' ? 'textarea' : 'text')).toLowerCase();
    const autocomplete = (el.getAttribute('autocomplete') || '').toLowerCase();

    // Confirm-password: fieldNN whose sibling fieldN (trailing 2 -> 1) exists.
    if (type === 'password' && /2$/.test(name)) {
      const primaryName = name.replace(/2$/, '1');
      if (form.elements[primaryName]) return { kind: 'confirm-password', primaryName };
    }
    if (type === 'password') return { kind: 'password' };

    if (type === 'email' || autocomplete === 'email' || name.includes('email')) return { kind: 'email' };

    if (name.includes('phone') || autocomplete === 'tel') return { kind: 'phone' };

    if (/license_?plate|reg(istration)?_?(no|number)?$|^plate$/.test(name)) return { kind: 'plate' };

    if (/license_?plate|plate/.test(name)) return { kind: 'plate' };

    if (type === 'number' || /(^|_)(quantity|qty|amount|price|stock|discount|mileage|cost)(_|$)/.test(name)) {
      return { kind: 'numeric' };
    }

    if (type === 'date') return { kind: 'date' };

    if (type === 'time') return { kind: 'time' };

    if (type === 'file') return { kind: 'file' };

    if (type === 'search' || name === 'q') return { kind: 'search' };

    const pattern = el.getAttribute('pattern') || '';
    if (
      /(^|_)(first_name|last_name|full_name|name)$/.test(name) ||
      pattern.includes("A-Za-z") && pattern.includes("-")
    ) {
      return { kind: 'name' };
    }

    if (el.tagName === 'TEXTAREA') return { kind: 'textarea' };

    return { kind: 'generic' };
  }

  /* ------------------------------------------------------------
     DOM helpers: wrap field, create feedback + status-icon nodes
     ------------------------------------------------------------ */
  function ensureWrap(el) {
    let wrap = el.closest('.field-wrap');
    if (wrap) return wrap;
    wrap = document.createElement('div');
    wrap.className = 'field-wrap';
    el.parentNode.insertBefore(wrap, el);
    wrap.appendChild(el);
    return wrap;
  }

  function ensureFeedback(el) {
    let fb = el._shFeedback;
    if (fb) return fb;
    fb = document.createElement('p');
    fb.className = 'field-feedback';
    el.insertAdjacentElement('afterend', fb);
    el._shFeedback = fb;
    return fb;
  }

  function ensureStatusIcon(wrap, el) {
    let icon = el._shStatusIcon;
    if (icon) return icon;
    icon = document.createElement('i');
    icon.className = 'field-status-icon fa-solid';
    wrap.appendChild(icon);
    el._shStatusIcon = icon;
    return icon;
  }

  function setState(el, wrap, state, message) {
    // state: 'valid' | 'invalid' | 'neutral'
    const fb = ensureFeedback(el);
    const icon = ensureStatusIcon(wrap, el);

    el.classList.remove('is-valid', 'is-invalid');
    icon.classList.remove('is-valid', 'is-invalid', 'is-shown', 'fa-check', 'fa-xmark');
    fb.classList.remove('is-error', 'is-success', 'is-shown');

    if (state === 'valid') {
      el.classList.add('is-valid');
      icon.classList.add('is-valid', 'is-shown', 'fa-check');
      if (message) {
        fb.innerHTML = '<i class="fa-solid fa-circle-check"></i><span>' + message + '</span>';
        fb.classList.add('is-success', 'is-shown');
      } else {
        fb.innerHTML = '';
      }
    } else if (state === 'invalid') {
      el.classList.add('is-invalid');
      icon.classList.add('is-invalid', 'is-shown', 'fa-xmark');
      fb.innerHTML = '<i class="fa-solid fa-circle-exclamation"></i><span>' + (message || 'This field looks invalid.') + '</span>';
      fb.classList.add('is-error', 'is-shown');
    } else {
      fb.innerHTML = '';
    }
  }

  /* ------------------------------------------------------------
     Keystroke guards -- block obviously-disallowed characters
     while still allowing control/navigation keys, selection,
     and keyboard shortcuts.
     ------------------------------------------------------------ */
  function guardKeydown(el, allowedCharRe) {
    el.addEventListener('keydown', (e) => {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      if (e.key.length !== 1) return; // backspace, tab, arrows, delete, etc.
      if (!allowedCharRe.test(e.key)) e.preventDefault();
    });
  }

  function guardPaste(el, sanitizeFn) {
    el.addEventListener('paste', (e) => {
      e.preventDefault();
      const text = (e.clipboardData || window.clipboardData).getData('text');
      const clean = sanitizeFn(text);
      const start = el.selectionStart ?? el.value.length;
      const end = el.selectionEnd ?? el.value.length;
      el.value = el.value.slice(0, start) + clean + el.value.slice(end);
      el.dispatchEvent(new Event('input', { bubbles: true }));
    });
  }

  /* ------------------------------------------------------------
     Per-kind setup
     ------------------------------------------------------------ */
  function setupPhone(el, wrap) {
    guardKeydown(el, /[0-9+]/);
    guardPaste(el, (t) => t.replace(/(?!^\+)[^\d]/g, '').replace(/(.+)\+/g, '$1'));
    const check = () => {
      const v = el.value.trim();
      if (!v) return setState(el, wrap, el.required ? 'invalid' : 'neutral', el.required ? 'Phone number is required.' : '');
      if (!PHONE_RE.test(v)) return setState(el, wrap, 'invalid', 'Enter a valid phone number (9–15 digits, optional leading +).');
      setState(el, wrap, 'valid', 'Looks good.');
    };
    el.addEventListener('input', debounce(check, 150));
    el.addEventListener('blur', check);
  }

  function setupEmail(el, wrap) {
    const check = () => {
      const v = el.value.trim();
      if (!v) return setState(el, wrap, el.required ? 'invalid' : 'neutral', el.required ? 'Email is required.' : '');
      if (!EMAIL_RE.test(v)) return setState(el, wrap, 'invalid', 'Enter a valid email address.');
      setState(el, wrap, 'valid', '');
    };
    el.addEventListener('input', debounce(check, 200));
    el.addEventListener('blur', check);
  }

  function setupName(el, wrap) {
    guardKeydown(el, /[A-Za-z\s\-']/);
    guardPaste(el, (t) => t.replace(/[^A-Za-z\s\-']/g, ''));
    const check = () => {
      const v = el.value.trim();
      if (!v) return setState(el, wrap, el.required ? 'invalid' : 'neutral', el.required ? 'This field is required.' : '');
      if (!NAME_RE.test(v)) return setState(el, wrap, 'invalid', 'Only letters, spaces, hyphens, and apostrophes are allowed.');
      setState(el, wrap, 'valid', '');
    };
    el.addEventListener('input', debounce(check, 150));
    el.addEventListener('blur', () => { el.value = el.value.trim(); check(); });
  }

  function setupNumeric(el, wrap) {
    const allowDecimal = (el.getAttribute('step') || '').includes('.') || el.getAttribute('step') === 'any';
    const allowNegative = parseFloat(el.getAttribute('min') || '0') < 0;
    guardKeydown(el, new RegExp('[0-9' + (allowDecimal ? '.' : '') + (allowNegative ? '\\-' : '') + ']'));
    guardPaste(el, (t) => {
      let clean = t.replace(allowDecimal ? /[^0-9.]/g : /[^0-9]/g, '');
      if (allowDecimal) {
        const parts = clean.split('.');
        clean = parts.shift() + (parts.length ? '.' + parts.join('') : '');
      }
      return clean;
    });
    const check = () => {
      const v = el.value.trim();
      if (!v) return setState(el, wrap, el.required ? 'invalid' : 'neutral', el.required ? 'This field is required.' : '');
      const num = parseFloat(v);
      if (Number.isNaN(num)) return setState(el, wrap, 'invalid', 'Numbers only.');
      const min = el.getAttribute('min');
      const max = el.getAttribute('max');
      if (min !== null && num < parseFloat(min)) return setState(el, wrap, 'invalid', `Must be ${min} or more.`);
      if (max !== null && num > parseFloat(max)) return setState(el, wrap, 'invalid', `Must be ${max} or less.`);
      setState(el, wrap, 'valid', '');
    };
    el.addEventListener('input', debounce(check, 150));
    el.addEventListener('blur', check);
  }

  function setupDate(el, wrap) {
    const check = () => {
      const v = el.value;
      if (!v) return setState(el, wrap, el.required ? 'invalid' : 'neutral', el.required ? 'Pick a date.' : '');
      const d = new Date(v + 'T00:00:00');
      if (Number.isNaN(d.getTime())) return setState(el, wrap, 'invalid', 'Enter a valid date.');
      const min = el.getAttribute('min');
      const max = el.getAttribute('max');
      if (min && v < min) return setState(el, wrap, 'invalid', `Date must be on or after ${min}.`);
      if (max && v > max) return setState(el, wrap, 'invalid', `Date must be on or before ${max}.`);
      setState(el, wrap, 'valid', '');
    };
    el.addEventListener('input', check);
    el.addEventListener('change', check);
    el.addEventListener('blur', check);
  }

  function setupTime(el, wrap) {
    const check = () => {
      const v = el.value;
      if (!v) return setState(el, wrap, el.required ? 'invalid' : 'neutral', el.required ? 'Pick a time.' : '');
      const min = el.getAttribute('min');
      const max = el.getAttribute('max');
      if (min && v < min) return setState(el, wrap, 'invalid', `Time must be at or after ${min}.`);
      if (max && v > max) return setState(el, wrap, 'invalid', `Time must be at or before ${max}.`);
      setState(el, wrap, 'valid', '');
    };
    el.addEventListener('input', check);
    el.addEventListener('change', check);
    el.addEventListener('blur', check);
  }

  function setupFile(el, wrap) {
    const accept = (el.getAttribute('accept') || '').split(',').map((s) => s.trim().toLowerCase()).filter(Boolean);
    const maxBytes = parseInt(el.getAttribute('data-max-size-mb') || '10', 10) * 1024 * 1024;

    let preview = el._shPreview;
    if (!preview) {
      preview = document.createElement('div');
      preview.className = 'file-preview';
      el.insertAdjacentElement('afterend', preview);
      el._shPreview = preview;
    }

    const matchesAccept = (file) => {
      if (!accept.length) return true;
      const name = file.name.toLowerCase();
      const mime = (file.type || '').toLowerCase();
      return accept.some((rule) => (rule.startsWith('.') ? name.endsWith(rule) : mime.startsWith(rule.replace('*', ''))));
    };

    const check = () => {
      preview.innerHTML = '';
      const file = el.files && el.files[0];
      if (!file) return setState(el, wrap, el.required ? 'invalid' : 'neutral', el.required ? 'Choose a file.' : '');

      if (!matchesAccept(file)) {
        el.value = '';
        return setState(el, wrap, 'invalid', `Unsupported file type. Allowed: ${accept.join(', ')}`);
      }
      if (file.size > maxBytes) {
        el.value = '';
        return setState(el, wrap, 'invalid', `File is too large (max ${Math.round(maxBytes / (1024 * 1024))}MB).`);
      }

      setState(el, wrap, 'valid', `${file.name} (${(file.size / 1024).toFixed(0)} KB)`);

      if (file.type && file.type.startsWith('image/')) {
        const img = document.createElement('img');
        img.className = 'file-preview-img';
        img.src = URL.createObjectURL(file);
        img.onload = () => URL.revokeObjectURL(img.src);
        preview.appendChild(img);
      }
    };
    el.addEventListener('change', check);
  }

  function setupPlate(el, wrap) {
    el.addEventListener('input', () => {
      const cursorAtEnd = el.selectionStart === el.value.length;
      el.value = el.value.toUpperCase();
      if (cursorAtEnd) { const len = el.value.length; el.setSelectionRange(len, len); }
    });
    guardKeydown(el, /[A-Za-z0-9\s\-]/);
    const check = () => {
      const compact = el.value.replace(/[\s\-]/g, '').toUpperCase();
      if (!compact) return setState(el, wrap, el.required ? 'invalid' : 'neutral', el.required ? 'License plate is required.' : '');
      if (!PLATE_RE.test(compact)) return setState(el, wrap, 'invalid', 'Enter a valid Kenyan plate, e.g. KDA 001A.');
      setState(el, wrap, 'valid', '');
    };
    el.addEventListener('input', debounce(check, 150));
    el.addEventListener('blur', () => {
      const compact = el.value.replace(/[\s\-]/g, '').toUpperCase();
      if (PLATE_RE.test(compact)) el.value = `${compact.slice(0, 3)} ${compact.slice(3, 6)}${compact[6]}`;
      check();
    });
  }

  function setupSearch(el) {
    el.addEventListener('blur', () => { el.value = el.value.trim().replace(/\s+/g, ' '); });
  }

  function setupTextarea(el, wrap) {
    const maxlength = el.getAttribute('maxlength');
    if (maxlength) {
      const counter = document.createElement('p');
      counter.className = 'char-counter';
      el.insertAdjacentElement('afterend', counter);
      const update = () => {
        const remaining = parseInt(maxlength, 10) - el.value.length;
        counter.textContent = `${el.value.length} / ${maxlength}`;
        counter.classList.toggle('is-near-limit', remaining <= 20 && remaining > 0);
        counter.classList.toggle('is-at-limit', remaining <= 0);
      };
      el.addEventListener('input', update);
      update();
    }
    if (el.hasAttribute('required')) {
      const check = () => {
        const v = el.value.trim();
        if (!v) return setState(el, wrap, 'invalid', 'This field is required.');
        const minlength = el.getAttribute('minlength');
        if (minlength && v.length < parseInt(minlength, 10)) {
          return setState(el, wrap, 'invalid', `Enter at least ${minlength} characters.`);
        }
        setState(el, wrap, 'valid', '');
      };
      el.addEventListener('input', debounce(check, 200));
      el.addEventListener('blur', check);
    }
  }

  function setupGeneric(el, wrap) {
    if (!el.hasAttribute('required')) return;
    const check = () => {
      const v = (el.value || '').trim();
      if (el.tagName === 'SELECT') {
        if (!v) return setState(el, wrap, 'invalid', 'Please make a selection.');
        return setState(el, wrap, 'valid', '');
      }
      if (!v) return setState(el, wrap, 'invalid', 'This field is required.');
      const minlength = el.getAttribute('minlength');
      if (minlength && v.length < parseInt(minlength, 10)) {
        return setState(el, wrap, 'invalid', `Enter at least ${minlength} characters.`);
      }
      setState(el, wrap, 'valid', '');
    };
    el.addEventListener('input', debounce(check, 200));
    el.addEventListener('blur', check);
    if (el.tagName === 'SELECT') el.addEventListener('change', check);
  }

  /* ------------------------------------------------------------
     Password strength + confirm-password matching
     ------------------------------------------------------------ */
  function pwRules(value) {
    return {
      length: value.length >= 8,
      upper: /[A-Z]/.test(value),
      lower: /[a-z]/.test(value),
      digit: /[0-9]/.test(value),
      special: PW_SPECIAL_RE.test(value),
    };
  }

  function setupPassword(el, wrap) {
    // The register page already has its own fancy meter wired up by
    // password-strength.js via [data-password-strength] — don't add a
    // second one there, just still track validity for the border state.
    const hasOwnMeter = el.hasAttribute('data-password-strength');
    let list, chip;
    if (!hasOwnMeter) {
      list = document.createElement('div');
      list.className = 'pw-rules';
      list.innerHTML = [
        ['length', '8+ characters'],
        ['upper', 'Uppercase letter'],
        ['lower', 'Lowercase letter'],
        ['digit', 'Number'],
        ['special', 'Special character'],
      ].map(([key, label]) => `<span class="pw-rule" data-rule="${key}"><i class="fa-solid fa-circle-dot"></i>${label}</span>`).join('');
      el.insertAdjacentElement('afterend', list);
    }

    const check = () => {
      const v = el.value;
      const rules = pwRules(v);
      if (list) {
        Object.keys(rules).forEach((key) => {
          chip = list.querySelector(`[data-rule="${key}"]`);
          if (!chip) return;
          const met = rules[key];
          chip.classList.toggle('is-met', met);
          chip.querySelector('i').className = met ? 'fa-solid fa-circle-check' : 'fa-solid fa-circle-dot';
        });
      }
      const allMet = Object.values(rules).every(Boolean);
      if (!v) return setState(el, wrap, el.required ? 'invalid' : 'neutral', '');
      if (!allMet) return setState(el, wrap, 'invalid', hasOwnMeter ? '' : 'Doesn\'t meet all requirements yet.');
      setState(el, wrap, 'valid', '');
      // Re-check confirm field once the primary password changes.
      const form = el.form;
      if (form) {
        const confirmName = (el.getAttribute('name') || '') + '2';
        const confirmEl = form.elements[confirmName];
        if (confirmEl && confirmEl._shRecheck) confirmEl._shRecheck();
      }
    };
    el.addEventListener('input', debounce(check, 120));
    el.addEventListener('blur', check);
  }

  function setupConfirmPassword(el, wrap, primaryName) {
    const check = () => {
      const form = el.form;
      const primary = form ? form.elements[primaryName] : null;
      const v = el.value;
      if (!v) return setState(el, wrap, el.required ? 'invalid' : 'neutral', '');
      if (!primary || v !== primary.value) return setState(el, wrap, 'invalid', 'Passwords do not match.');
      setState(el, wrap, 'valid', 'Passwords match.');
    };
    el._shRecheck = check;
    el.addEventListener('input', debounce(check, 120));
    el.addEventListener('blur', check);
  }

  /* ------------------------------------------------------------
     Required-field asterisk (auto-injected, Task 11)
     ------------------------------------------------------------ */
  function markRequiredLabel(el) {
    if (!el.hasAttribute('required') || !el.id) return;
    const label = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
    if (label && !label.querySelector('.required-mark')) {
      const mark = document.createElement('span');
      mark.className = 'required-mark';
      mark.textContent = '*';
      mark.setAttribute('aria-hidden', 'true');
      label.appendChild(mark);
    }
  }

  /* ------------------------------------------------------------
     Submit button loading state (Task 11/12) — applies to every
     form automatically; only engages once the browser is actually
     about to navigate/submit, and never blocks a form the user has
     filled out correctly.
     ------------------------------------------------------------ */
  function setupSubmitLoading(form) {
    form.addEventListener('submit', () => {
      const btn = form.querySelector('button[type="submit"], input[type="submit"]');
      if (!btn || btn.classList.contains('is-loading')) return;
      btn.classList.add('is-loading');
      btn.disabled = true;
      if (btn.tagName === 'BUTTON' && !btn.querySelector('.btn-spinner')) {
        const spinner = document.createElement('span');
        spinner.className = 'btn-spinner';
        btn.appendChild(spinner);
      }
    });
  }

  /* ------------------------------------------------------------
     Wire up one field
     ------------------------------------------------------------ */
  function wireField(el, form) {
    if (el._shWired) return;
    el._shWired = true;

    // Some templates (register.html) ship their own bespoke, fully-featured
    // validation script for a handful of fields. Marking those fields
    // data-manual-validation keeps this global engine from double-wiring
    // them -- without it, ensureWrap()/ensureFeedback() below would inject
    // a second set of status icons and feedback text right on top of the
    // page's own, breaking the layout and producing conflicting messages.
    if (el.hasAttribute('data-manual-validation')) return;

    const type = (el.getAttribute('type') || '').toLowerCase();
    if (['hidden', 'submit', 'button', 'reset', 'checkbox', 'radio', 'range', 'color'].includes(type)) return;

    const { kind, primaryName } = classify(el, form);
    const wrap = ensureWrap(el);

    markRequiredLabel(el);

    switch (kind) {
      case 'phone': return setupPhone(el, wrap);
      case 'email': return setupEmail(el, wrap);
      case 'name': return setupName(el, wrap);
      case 'numeric': return setupNumeric(el, wrap);
      case 'date': return setupDate(el, wrap);
      case 'time': return setupTime(el, wrap);
      case 'file': return setupFile(el, wrap);
      case 'plate': return setupPlate(el, wrap);
      case 'search': return setupSearch(el);
      case 'textarea': return setupTextarea(el, wrap);
      case 'password': return setupPassword(el, wrap);
      case 'confirm-password': return setupConfirmPassword(el, wrap, primaryName);
      default: return setupGeneric(el, wrap);
    }
  }

  function wireForm(form) {
    if (form._shWired) return;
    form._shWired = true;
    const fields = form.querySelectorAll('input, select, textarea');
    fields.forEach((el) => wireField(el, form));
    setupSubmitLoading(form);
  }

  function init() {
    document.querySelectorAll('form').forEach(wireForm);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Expose a small API in case a template ever wants to re-scan after
  // injecting a form dynamically (e.g. a modal loaded via fetch).
  window.ShineHubValidation = { scan: init };
})();
