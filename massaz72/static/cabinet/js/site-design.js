(() => {
  const form = document.getElementById('site-design-form');
  const themeButton = document.getElementById('design-theme');
  const page = document.getElementById('design-page');
  const deviceButtons = form.querySelectorAll('[data-preview-width]');
  const frame = document.getElementById('design-preview');
  const colors = [...form.querySelectorAll('[data-theme-color]')];
  let theme = 'light';

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

  function openPicker(input) {
    closePicker();
    const row = input.closest('.site-designer__color-row');
    const trigger = row.querySelector('.site-designer__color-trigger');
    active = { input, trigger, originalColor: input.value };
    label.textContent = trigger.textContent.trim();
    hex.value = input.value;
    readColor(input.value);
    paintPicker();
    row.append(picker);
    picker.hidden = false;
    trigger.setAttribute('aria-expanded', 'true');
  }

  for (const input of colors) {
    const trigger = input.closest('.site-designer__color-row').querySelector('.site-designer__color-trigger');
    input.closest('label').hidden = true;
    trigger.hidden = false;
    trigger.addEventListener('click', () => {
      if (active?.input === input) closePicker();
      else openPicker(input);
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
  document.addEventListener('click', event => {
    if (!event.target.closest('#design-color-picker, .site-designer__color-trigger')) closePicker();
  });

  function applyPalette() {
    for (const input of colors) {
      input.closest('.site-designer__color-row').style.setProperty('--current-color', input.value);
    }
    const doc = frame.contentDocument;
    if (!doc?.getElementById('site-palette')) return;

    doc.documentElement.dataset.theme = theme;
    for (const input of colors) {
      if (input.dataset.themeColor === theme) {
        doc.documentElement.style.setProperty(input.dataset.cssVariable, input.value);
      }
    }
  }

  const eyedropper = document.getElementById('design-eyedropper');
  const feedback = document.getElementById('design-eyedropper-feedback');
  let picking = false;
  let highlighted = null;

  function highlight(element) {
    highlighted?.removeAttribute('data-eyedropper-target');
    highlighted = element;
    highlighted?.setAttribute('data-eyedropper-target', '');
  }

  function setPicking(enabled, message = '') {
    picking = enabled;
    eyedropper.setAttribute('aria-pressed', String(enabled));
    frame.contentDocument?.documentElement.toggleAttribute('data-eyedropper', enabled);
    if (!enabled) highlight(null);
    feedback.textContent = message;
    feedback.hidden = !message;
  }

  function normalizeColor(value) {
    const rgb = value.match(/^rgb\(\s*(\d+),\s*(\d+),\s*(\d+)\s*\)$/);
    return rgb ? '#' + rgb.slice(1).map(channel => Number(channel).toString(16).padStart(2, '0')).join('') : null;
  }

  function clickedText(event) {
    const range = event.target.ownerDocument.createRange();
    return [...event.target.childNodes].some(node => {
      if (node.nodeType !== Node.TEXT_NODE || !node.textContent.trim()) return false;
      range.selectNodeContents(node);
      return [...range.getClientRects()].some(rect =>
        event.clientX >= rect.left && event.clientX <= rect.right &&
        event.clientY >= rect.top && event.clientY <= rect.bottom);
    });
  }

  function paletteInput(event) {
    const target = event.target;
    const matchingTheme = colors.filter(input => input.dataset.themeColor === theme);
    const control = variable => matchingTheme.find(input => input.dataset.cssVariable === variable);
    const inlineStyle = target.ownerDocument.defaultView;
    const text = clickedText(event);
    if (target.closest('.redesign-hero .massage__cta')) {
      return control(text ? '--redesign-booking-text' : '--redesign-booking-glow');
    }
    if (target.closest('img, video, canvas, svg')) return undefined;

    const match = (value, names) => {
      const hexColor = normalizeColor(value);
      return hexColor && names.map(control).find(input => input?.value === hexColor);
    };
    if (text) {
      return match(inlineStyle.getComputedStyle(target).color, [
        '--color-ink', '--color-body', '--color-muted', '--color-primary',
        '--color-on-primary', '--redesign-hero-text',
      ]);
    }
    for (let element = target; element; element = element.parentElement) {
      const style = inlineStyle.getComputedStyle(element);
      if (style.backgroundImage !== 'none') return undefined;
      if (style.backgroundColor === 'rgba(0, 0, 0, 0)') continue;
      const preferred = [
        ['.header', '--color-header-bg'],
        ['.redesign-hero', '--redesign-hero-bg'],
        ['.redesign-hero__directions', '--redesign-navigation'],
        ['.service-card, input, select', '--color-canvas-card'],
      ].find(([selector]) => element.matches(selector));
      return (preferred && control(preferred[1])) || match(style.backgroundColor, [
        '--color-canvas', '--color-canvas-card', '--color-surface-soft', '--color-primary',
        '--color-header-bg', '--redesign-hero-bg', '--redesign-navigation',
      ]);
    }
    return undefined;
  }

  eyedropper.addEventListener('click', () => {
    closePicker();
    setPicking(!picking, picking ? '' : 'Нажмите на цвет в предпросмотре. Esc отменяет выбор.');
  });
  function handleEscape(event) {
    if (event.key !== 'Escape') return;
    if (picking) {
      setPicking(false);
      eyedropper.focus();
    } else if (active) {
      active.input.value = active.originalColor;
      closePicker(true);
      applyPalette();
    }
  }

  document.addEventListener('keydown', handleEscape);

  themeButton.addEventListener('click', () => {
    closePicker();
    theme = theme === 'light' ? 'dark' : 'light';
    themeButton.setAttribute('aria-pressed', String(theme === 'dark'));
    for (const section of form.querySelectorAll('[data-theme-fields]')) {
      section.hidden = section.dataset.themeFields !== theme;
    }
    applyPalette();
  });

  function choosePage() {
    setPicking(false);
    eyedropper.disabled = true;
    const url = new URL(page.value, window.location.origin);
    url.searchParams.set('design_preview', '1');
    frame.src = url.href;
  }

  frame.addEventListener('load', () => {
    const doc = frame.contentDocument;
    if (!doc?.getElementById('site-palette')) return;
    const cursorStyle = doc.createElement('style');
    cursorStyle.textContent = '[data-eyedropper], [data-eyedropper] * { cursor: crosshair !important; }' +
      '[data-eyedropper-target] { outline: 2px solid #ba527b !important; outline-offset: -2px !important; }';
    doc.head.append(cursorStyle);
    eyedropper.disabled = false;
    doc.addEventListener('pointermove', event => {
      if (picking && highlighted !== event.target) highlight(event.target);
    });
    doc.addEventListener('pointerleave', () => highlight(null));
    doc.addEventListener('keydown', handleEscape);
    doc.addEventListener('submit', event => {
      event.preventDefault();
      event.stopImmediatePropagation();
    }, true);
    doc.addEventListener('click', event => {
      if (picking) {
        event.preventDefault();
        event.stopImmediatePropagation();
        const input = paletteInput(event);
        if (!input) {
          feedback.textContent = 'У этого фрагмента нет цвета из палитры. Выберите другой элемент.';
          return;
        }
        setPicking(false, 'Выбран цвет «' + input.closest('label').textContent.trim() + '».');
        openPicker(input);
        active.trigger.scrollIntoView({ block: 'nearest' });
        active.trigger.focus({ preventScroll: true });
        return;
      }
      closePicker();
      if (event.target.closest('a, .js-theme-toggle, .accept-cookies, .cookie-details')) {
        event.preventDefault();
        event.stopImmediatePropagation();
      }
    }, true);
    applyPalette();
  });
  form.addEventListener('input', applyPalette);
  page.addEventListener('change', choosePage);
  for (const button of deviceButtons) {
    button.addEventListener('click', () => {
      for (const option of deviceButtons) {
        option.setAttribute('aria-pressed', String(option === button));
      }
      frame.classList.toggle('site-designer__frame--mobile', button.dataset.previewWidth === 'mobile');
    });
  }
  document.getElementById('design-reset').addEventListener('click', () => {
    for (const input of colors) {
      if (input.dataset.themeColor === theme) input.value = input.dataset.defaultColor;
    }
    applyPalette();
  });
  applyPalette();
  choosePage();
})();
