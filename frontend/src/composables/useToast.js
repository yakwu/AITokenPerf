function getContainer() {
  let c = document.querySelector('.toast-container');
  if (!c) {
    c = document.createElement('div');
    c.className = 'toast-container';
    document.body.appendChild(c);
  }
  return c;
}

export function toast(msg, type = 'info', opts = {}) {
  const el = document.createElement('div');
  el.className = 'toast ' + type;
  el.textContent = msg;
  if (opts.onClick) {
    el.style.cursor = 'pointer';
    el.addEventListener('click', () => {
      opts.onClick();
      el.remove();
    });
  }
  getContainer().appendChild(el);
  const duration = opts.duration || 3000;
  setTimeout(() => {
    el.style.opacity = '0';
    el.style.transform = 'translateX(20px)';
    el.style.transition = 'opacity 0.3s, transform 0.3s';
    setTimeout(() => el.remove(), 300);
  }, duration);
}
