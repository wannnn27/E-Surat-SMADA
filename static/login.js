(() => {
  'use strict';

  const passwordInput = document.getElementById('login-password');
  const passwordToggle = document.querySelector('[data-password-toggle]');

  if (passwordInput && passwordToggle) {
    passwordToggle.addEventListener('click', () => {
      const isVisible = passwordInput.type === 'text';
      passwordInput.type = isVisible ? 'password' : 'text';
      passwordToggle.setAttribute('aria-pressed', String(!isVisible));
      passwordToggle.setAttribute('aria-label', isVisible ? 'Tampilkan password' : 'Sembunyikan password');

      const icon = passwordToggle.querySelector('i');
      if (icon) {
        icon.classList.toggle('fa-eye', isVisible);
        icon.classList.toggle('fa-eye-slash', !isVisible);
      }

      passwordInput.focus({ preventScroll: true });
      const cursorPosition = passwordInput.value.length;
      passwordInput.setSelectionRange(cursorPosition, cursorPosition);
    });
  }

  const loginForm = document.querySelector('.login-form');
  const submitButton = document.querySelector('.login-submit');

  if (loginForm && submitButton) {
    loginForm.addEventListener('submit', () => {
      submitButton.disabled = true;
      submitButton.classList.add('is-loading');

      const label = submitButton.querySelector('span');
      const icon = submitButton.querySelector('i');
      if (label) label.textContent = 'Memeriksa akun...';
      if (icon) icon.className = 'fa-solid fa-circle-notch fa-spin';
    });
  }
})();
