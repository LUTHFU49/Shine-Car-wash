(function () {
  function getCookie(name) {
    const match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
    return match ? decodeURIComponent(match[2]) : null;
  }

  document.addEventListener('DOMContentLoaded', () => {
    const input = document.getElementById('photo-upload-input');
    const removeBtn = document.getElementById('photo-remove-btn');
    const img = document.getElementById('profile-photo-img');
    const placeholder = document.getElementById('profile-photo-placeholder');
    const errorEl = document.getElementById('photo-upload-error');
    const csrftoken = getCookie('csrftoken');

    if (input) {
      input.addEventListener('change', async () => {
        const file = input.files[0];
        if (!file) return;

        errorEl.classList.add('hidden');
        const formData = new FormData();
        formData.append('profile_photo', file);

        try {
          const response = await fetch('/accounts/profile/photo/upload/', {
            method: 'POST',
            headers: { 'X-CSRFToken': csrftoken },
            body: formData,
          });
          const data = await response.json();

          if (data.success) {
            img.src = data.photo_url + '?t=' + Date.now();
            img.classList.remove('hidden');
            if (placeholder) placeholder.classList.add('hidden');
            if (window.showToast) window.showToast('Profile photo updated.', 'success');
          } else {
            errorEl.textContent = (data.errors && data.errors[0]) || 'Upload failed.';
            errorEl.classList.remove('hidden');
          }
        } catch (err) {
          errorEl.textContent = 'Upload failed. Please try again.';
          errorEl.classList.remove('hidden');
        }
      });
    }

    if (removeBtn) {
      removeBtn.addEventListener('click', async () => {
        try {
          const response = await fetch('/accounts/profile/photo/remove/', {
            method: 'POST',
            headers: { 'X-CSRFToken': csrftoken },
          });
          const data = await response.json();
          if (data.success) {
            if (img) img.classList.add('hidden');
            if (placeholder) placeholder.classList.remove('hidden');
            if (window.showToast) window.showToast('Profile photo removed.', 'success');
          }
        } catch (err) {
          if (window.showToast) window.showToast('Could not remove photo.', 'error');
        }
      });
    }
  });
})();
