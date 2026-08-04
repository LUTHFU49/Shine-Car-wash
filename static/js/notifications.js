/*
 * Real-time notification bell: connects to /ws/notifications/ over
 * Django Channels and updates the topbar badge + dropdown live, no
 * page reload or polling needed for the common case. Falls back to
 * polling /notifications/unread-count/ only while the socket is
 * down (first connect attempt, or a dropped connection before it
 * reconnects) so the badge is never wrong for long either way.
 */
(function () {
  const badge = document.querySelector('[data-notification-badge]');
  const root = document.querySelector('[data-notification-root]');
  if (!badge || !root) return;

  const toggleButton = root.querySelector('[data-notification-bell-toggle]');
  const dropdown = root.querySelector('[data-notification-dropdown]');
  const itemsContainer = root.querySelector('[data-notification-items]');
  const markAllButton = root.querySelector('[data-notification-mark-all]');

  let pollTimer = null;
  let socket = null;
  let reconnectDelay = 1000;

  function getCsrfToken() {
    const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? match[1] : '';
  }

  function setBadge(count) {
    if (count > 0) {
      badge.textContent = count > 99 ? '99+' : String(count);
      badge.classList.remove('hidden');
      badge.classList.add('flex');
    } else {
      badge.classList.add('hidden');
      badge.classList.remove('flex');
    }
  }

  function levelDot(level) {
    return { danger: 'bg-[var(--color-pink)]', warning: 'bg-amber-500', success: 'bg-green-500' }[level] || 'bg-[var(--color-blue)]';
  }

  function renderItems(results) {
    if (!results.length) {
      itemsContainer.innerHTML = '<p class="px-4 py-6 text-sm text-ink-soft text-center">You\'re all caught up.</p>';
      return;
    }
    itemsContainer.innerHTML = results.map((n) => `
      <div class="px-4 py-3 flex items-start gap-2.5 ${n.is_read ? '' : 'bg-surface-alt/50'}" data-notification-item data-public-id="${n.public_id}" data-url="${n.url || ''}">
        <span class="mt-1 w-1.5 h-1.5 rounded-full shrink-0 ${levelDot(n.level)}"></span>
        <div class="flex-1 min-w-0 cursor-pointer">
          <p class="text-sm font-medium text-ink truncate">${n.title}</p>
          ${n.message ? `<p class="text-xs text-ink-soft mt-0.5 line-clamp-2">${n.message}</p>` : ''}
          <p class="text-[11px] text-ink-soft mt-1">${n.created_at}</p>
        </div>
      </div>
    `).join('');

    itemsContainer.querySelectorAll('[data-notification-item]').forEach((el) => {
      el.addEventListener('click', () => {
        const publicId = el.getAttribute('data-public-id');
        const url = el.getAttribute('data-url');
        markRead(publicId).finally(() => {
          if (url) window.location.href = url;
        });
      });
    });
  }

  function loadRecent() {
    fetch('/notifications/recent/', { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then((response) => (response.ok ? response.json() : null))
      .then((data) => {
        if (!data) return;
        renderItems(data.results);
        setBadge(data.unread_count);
      })
      .catch(() => {});
  }

  function markRead(publicId) {
    return fetch(`/notifications/read/${publicId}/`, {
      method: 'POST',
      headers: { 'X-CSRFToken': getCsrfToken(), 'X-Requested-With': 'XMLHttpRequest' },
    }).then(() => loadRecent());
  }

  markAllButton?.addEventListener('click', (event) => {
    event.stopPropagation();
    fetch('/notifications/read-all/', {
      method: 'POST',
      headers: { 'X-CSRFToken': getCsrfToken(), 'X-Requested-With': 'XMLHttpRequest' },
    }).then(() => loadRecent());
  });

  toggleButton?.addEventListener('click', (event) => {
    event.stopPropagation();
    const isHidden = dropdown.classList.contains('hidden');
    if (isHidden) {
      dropdown.classList.remove('hidden');
      toggleButton.setAttribute('aria-expanded', 'true');
      loadRecent();
    } else {
      dropdown.classList.add('hidden');
      toggleButton.setAttribute('aria-expanded', 'false');
    }
  });

  document.addEventListener('click', (event) => {
    if (!root.contains(event.target)) {
      dropdown.classList.add('hidden');
      toggleButton?.setAttribute('aria-expanded', 'false');
    }
  });

  // ---- Polling fallback (only runs while the socket is not open) ----

  function pollOnce() {
    fetch('/notifications/unread-count/', { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then((response) => (response.ok ? response.json() : null))
      .then((data) => data && setBadge(data.unread_count))
      .catch(() => {});
  }

  function startPolling() {
    if (pollTimer) return;
    pollOnce();
    pollTimer = setInterval(pollOnce, 30000);
  }

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  // ---- WebSocket connection with auto-reconnect ----

  function connectSocket() {
    const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
    socket = new WebSocket(`${scheme}://${window.location.host}/ws/notifications/`);

    socket.addEventListener('open', () => {
      reconnectDelay = 1000;
      stopPolling();
    });

    socket.addEventListener('message', (event) => {
      const data = JSON.parse(event.data);
      if (data.event === 'unread_count') {
        setBadge(data.count);
      } else if (data.event === 'notification') {
        if (typeof showToast === 'function') {
          const tagMap = { danger: 'error', warning: 'warning', success: 'success', info: 'info' };
          showToast(data.notification.title, tagMap[data.notification.level] || 'info');
        }
        if (!dropdown.classList.contains('hidden')) {
          loadRecent();
        }
      }
    });

    socket.addEventListener('close', () => {
      startPolling();
      setTimeout(connectSocket, reconnectDelay);
      reconnectDelay = Math.min(reconnectDelay * 2, 30000);
    });

    socket.addEventListener('error', () => {
      socket.close();
    });
  }

  startPolling();
  connectSocket();
})();
