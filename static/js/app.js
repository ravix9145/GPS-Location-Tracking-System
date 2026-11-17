(() => {
  const root = document.documentElement;
  const toggle = document.getElementById('themeToggle');
  const setThemeLabel = () => {
    if (!toggle) return;
    const isDark = root.dataset.theme !== 'light';
    const symbol = toggle.querySelector('.theme-symbol');
    if (symbol) symbol.textContent = isDark ? '☼' : '☾';
  };
  try {
    const saved = localStorage.getItem('gps-theme');
    if (saved === 'light' || saved === 'dark') root.dataset.theme = saved;
  } catch (_) {}
  setThemeLabel();
  if (toggle) toggle.addEventListener('click', () => {
    root.dataset.theme = root.dataset.theme === 'dark' ? 'light' : 'dark';
    try { localStorage.setItem('gps-theme', root.dataset.theme); } catch (_) {}
    setThemeLabel();
  });
  document.querySelectorAll('[data-toggle-password]').forEach(button => {
    button.addEventListener('click', () => {
      const input = document.getElementById(button.dataset.togglePassword);
      if (!input) return;
      const show = input.type === 'password';
      input.type = show ? 'text' : 'password';
      button.textContent = show ? 'Hide' : 'Show';
    });
  });
  document.querySelectorAll('.flash').forEach(item => {
    window.setTimeout(() => { item.classList.add('flash-hide'); window.setTimeout(() => item.remove(), 350); }, 5500);
  });
})();

async function apiRequest(url, options = {}) {
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
  const headers = { ...(options.headers || {}), 'X-CSRF-Token': csrf };
  if (options.body && typeof options.body !== 'string') {
    headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(options.body);
  }
  const response = await fetch(url, { ...options, headers });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
  return data;
}
