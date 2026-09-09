(() => {
  'use strict';

  const csrfForms = Array.from(
    document.querySelectorAll('form[method="post"], form[method="POST"]')
  ).filter((form) => form.querySelector('input[name="_csrf_token"], input[name="csrf_token"]'));

  if (!csrfForms.length) return;

  const preparedForms = new WeakSet();
  let refreshPromise = null;

  function applyToken(token) {
    if (!token) return;
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) meta.content = token;
    document.querySelectorAll('input[name="_csrf_token"], input[name="csrf_token"]').forEach((input) => {
      input.value = token;
    });
  }

  function refreshToken() {
    if (refreshPromise) return refreshPromise;
    refreshPromise = fetch('/api/csrf', {
      method: 'GET',
      cache: 'no-store',
      credentials: 'same-origin',
      headers: { Accept: 'application/json' }
    })
      .then((response) => {
        if (!response.ok) throw new Error('Sesi tidak dapat diperbarui');
        return response.json();
      })
      .then((payload) => {
        if (!payload || !payload.csrf_token) throw new Error('Token sesi tidak tersedia');
        applyToken(payload.csrf_token);
        return payload.csrf_token;
      })
      .finally(() => {
        refreshPromise = null;
      });
    return refreshPromise;
  }

  csrfForms.forEach((form) => {
    form.addEventListener('submit', async (event) => {
      if (preparedForms.has(form)) {
        preparedForms.delete(form);
        return;
      }

      event.preventDefault();
      const submitter = event.submitter;
      if (submitter) submitter.disabled = true;

      try {
        await refreshToken();
      } catch (_error) {
        // Server tetap menangani token kedaluwarsa dengan halaman/redirect yang ramah.
      }

      preparedForms.add(form);
      if (submitter) submitter.disabled = false;
      form.requestSubmit(submitter || undefined);
    });
  });

  window.addEventListener('pageshow', () => void refreshToken().catch(() => {}));
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') void refreshToken().catch(() => {});
  });
})();
