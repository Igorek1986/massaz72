(() => {
  const form = document.getElementById('site-design-form');
  const theme = document.getElementById('design-theme');
  const page = document.getElementById('design-page');
  const width = document.getElementById('design-width');
  const frame = document.getElementById('design-preview');
  const colors = [...form.querySelectorAll('[data-theme-color]')];

  function applyPalette() {
    const doc = frame.contentDocument;
    if (!doc?.getElementById('site-palette')) return;

    doc.documentElement.dataset.theme = theme.value;
    for (const input of colors) {
      if (input.dataset.themeColor === theme.value) {
        doc.documentElement.style.setProperty(input.dataset.cssVariable, input.value);
      }
    }
  }

  function chooseTheme() {
    for (const section of form.querySelectorAll('[data-theme-fields]')) {
      section.hidden = section.dataset.themeFields !== theme.value;
    }
    applyPalette();
  }

  function choosePage() {
    const url = new URL(page.value, window.location.origin);
    url.searchParams.set('design_preview', '1');
    frame.src = url.href;
  }

  frame.addEventListener('load', () => {
    const doc = frame.contentDocument;
    if (!doc?.getElementById('site-palette')) return;
    doc.addEventListener('click', event => {
      if (event.target.closest('a, .js-theme-toggle, .accept-cookies, .cookie-details')) {
        event.preventDefault();
        event.stopImmediatePropagation();
      }
    }, true);
    applyPalette();
  });
  form.addEventListener('input', applyPalette);
  theme.addEventListener('change', chooseTheme);
  page.addEventListener('change', choosePage);
  width.addEventListener('change', () => frame.classList.toggle('site-designer__frame--mobile', width.value === 'mobile'));
  document.getElementById('design-reset').addEventListener('click', () => {
    for (const input of colors) {
      if (input.dataset.themeColor === theme.value) input.value = input.dataset.defaultColor;
    }
    applyPalette();
  });
  choosePage();
})();
