(() => {
  const form = document.getElementById('site-design-form');
  const theme = document.getElementById('design-theme');
  const page = document.getElementById('design-page');
  const width = document.getElementById('design-width');
  const frame = document.getElementById('design-preview');
  const colors = [...form.querySelectorAll('[data-theme-color]')];

  const picker = document.getElementById('design-color-picker');
  const plane = picker.querySelector('[data-picker-plane]');
  const hue = picker.querySelector('[data-picker-hue]');
  const hex = picker.querySelector('[data-picker-hex]');
  const label = document.getElementById('design-color-label');
  let active = null;
  let saturation = 0;
  let brightness = 0;
  let angle = 0;

  function closePicker(restoreFocus = false) {
    if (!active) return;
    active.trigger.setAttribute('aria-expanded', 'false');
    if (restoreFocus) active.trigger.focus();
    picker.hidden = true;
    active = null;
  }

  function readColor(value) {
    const [r, g, b] = value.slice(1).match(/../g).map(channel => parseInt(channel, 16) / 255);
    brightness = Math.max(r, g, b);
    const delta = brightness - Math.min(r, g, b);
    saturation = brightness ? delta / brightness : 0;
    if (!delta) {
      angle = 0;
    } else {
      const sector = brightness === r ? (g - b) / delta :
        brightness === g ? (b - r) / delta + 2 : (r - g) / delta + 4;
      angle = (sector * 60 + 360) % 360;
    }
  }

  function paintPicker() {
    hue.value = Math.min(359, Math.round(angle));
    plane.style.setProperty('--picker-hue', angle);
    plane.style.setProperty('--picker-s', `${saturation * 100}%`);
    plane.style.setProperty('--picker-y', `${(1 - brightness) * 100}%`);
  }

  function updateColor() {
    const channel = offset => {
      const sector = (offset + angle / 60) % 6;
      const light = brightness * (1 - saturation * Math.max(0, Math.min(sector, 4 - sector, 1)));
      return Math.round(light * 255).toString(16).padStart(2, '0');
    };
    active.input.value = '#' + [5, 3, 1].map(channel).join('');
    hex.value = active.input.value;
    paintPicker();
    applyPalette();
  }

  for (const input of colors) {
    const row = input.closest('.site-designer__color-row');
    const trigger = row.querySelector('.site-designer__color-trigger');
    input.closest('label').hidden = true;
    trigger.hidden = false;
    trigger.addEventListener('click', () => {
      if (active?.input === input) {
        closePicker();
        return;
      }
      closePicker();
      active = { input, trigger };
      label.textContent = trigger.textContent.trim();
      hex.value = input.value;
      readColor(input.value);
      paintPicker();
      row.append(picker);
      picker.hidden = false;
      trigger.setAttribute('aria-expanded', 'true');
    });
  }

  const clamp = value => Math.max(0, Math.min(1, value));

  function choosePlaneColor(event) {
    const rect = plane.getBoundingClientRect();
    saturation = clamp((event.clientX - rect.left) / rect.width);
    brightness = clamp(1 - (event.clientY - rect.top) / rect.height);
    updateColor();
  }

  plane.addEventListener('pointerdown', event => {
    plane.setPointerCapture(event.pointerId);
    choosePlaneColor(event);
  });
  plane.addEventListener('pointermove', event => {
    if (plane.hasPointerCapture(event.pointerId)) choosePlaneColor(event);
  });
  plane.addEventListener('keydown', event => {
    const steps = { ArrowLeft: [-.025, 0], ArrowRight: [.025, 0], ArrowDown: [0, -.025], ArrowUp: [0, .025] };
    if (!steps[event.key]) return;
    event.preventDefault();
    saturation = clamp(saturation + steps[event.key][0]);
    brightness = clamp(brightness + steps[event.key][1]);
    updateColor();
  });

  hue.addEventListener('input', () => {
    angle = Number(hue.value);
    updateColor();
  });
  hex.addEventListener('input', () => {
    const value = '#' + hex.value.trim().replace(/^#/, '');
    if (!/^#[0-9a-f]{6}$/i.test(value)) return;
    active.input.value = value;
    readColor(active.input.value);
    paintPicker();
  });
  hex.addEventListener('blur', () => { if (active) hex.value = active.input.value; });
  picker.querySelector('[data-picker-close]').addEventListener('click', () => closePicker(true));
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') closePicker(true);
  });
  document.addEventListener('click', event => {
    if (!event.target.closest('#design-color-picker, .site-designer__color-trigger')) closePicker();
  });

  function applyPalette() {
    for (const input of colors) {
      input.closest('.site-designer__color-row').style.setProperty('--current-color', input.value);
    }
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
    closePicker();
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
      closePicker();
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
  applyPalette();
  choosePage();
})();
