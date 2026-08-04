/* Selector de tema compartido: claro -> oscuro -> según el sistema.
 *
 * Las dos páginas lo usan igual. El mapa además necesita repintar el canvas
 * cuando cambia el tema, así que puede pasar un callback.
 */

const THEME_MODES = ['light', 'dark', 'system'];
const THEME_LABEL = {
  light:  'Tema claro',
  dark:   'Tema oscuro',
  system: 'Según el sistema',
};
const THEME_ICON = {
  light: '<circle cx="12" cy="12" r="4.5"/><path d="M12 2.5v2M12 19.5v2M4.6 4.6l1.4 1.4' +
         'M18 18l1.4 1.4M2.5 12h2M19.5 12h2M4.6 19.4L6 18M18 6l1.4-1.4"/>',
  dark:  '<path d="M20.5 14.6A8.6 8.6 0 1 1 9.4 3.5a6.7 6.7 0 0 0 11.1 11.1z"/>',
  system: '<rect x="2.5" y="4" width="19" height="13" rx="2"/><path d="M8.5 21h7M12 17v4"/>',
};

const darkMode = window.matchMedia('(prefers-color-scheme: dark)');

let themeMode = 'system';
try {
  const saved = localStorage.getItem('theme');
  if (THEME_MODES.includes(saved)) themeMode = saved;
} catch (e) { /* localStorage bloqueado */ }

const isDark = () => themeMode === 'dark' || (themeMode === 'system' && darkMode.matches);

/** Conecta el botón. `onChange` corre después de cada cambio de tema. */
function initTheme(button, onChange) {
  function render() {
    const label = THEME_LABEL[themeMode];
    button.innerHTML =
      `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" ` +
      `stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">` +
      `${THEME_ICON[themeMode]}</svg>`;
    button.title = `${label} — clic para cambiar`;
    button.setAttribute('aria-label', label);
  }

  function setTheme(mode) {
    themeMode = mode;
    if (mode === 'system') delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = mode;
    try { localStorage.setItem('theme', mode); } catch (e) { /* bloqueado */ }
    render();
    if (onChange) onChange();
  }

  button.addEventListener('click', () => {
    setTheme(THEME_MODES[(THEME_MODES.indexOf(themeMode) + 1) % THEME_MODES.length]);
  });

  // Si el tema quedó atado al sistema, hay que seguirlo cuando cambia.
  darkMode.addEventListener('change', () => {
    if (themeMode === 'system' && onChange) onChange();
  });

  render();
  return setTheme;
}
