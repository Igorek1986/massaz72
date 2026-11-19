(() => {
  const script = document.currentScript;
  const root = document.querySelector("[data-push-url]");
  const section = root?.closest("[data-push-section]");
  const isAppleMobile = /iPhone|iPad|iPod/.test(navigator.userAgent)
    || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  const standalone = navigator.standalone === true || matchMedia("(display-mode: standalone)").matches;
  const worker = window.isSecureContext && "serviceWorker" in navigator
    ? navigator.serviceWorker.register(script.dataset.worker, { updateViaCache: "none" }).catch(() => null)
    : null;
  if (!root || !isAppleMobile) return;

  root.hidden = false;
  section.hidden = false;
  const status = root.querySelector("[data-push-status]");
  if (!standalone) {
    status.textContent = "В Safari нажмите «Поделиться» → «На экран “Домой”». Затем откройте приложение с экрана «Домой» и вернитесь сюда.";
    return;
  }
  if (!window.isSecureContext || !("Notification" in window) || !("PushManager" in window)
      || !("serviceWorker" in navigator)) {
    status.textContent = "Для уведомлений нужен iPhone или iPad с iOS 16.4 или новее и подключение по HTTPS.";
    return;
  }

  const form = root.querySelector("form");
  const consent = form.querySelector("input[type=checkbox]");
  const consentLabel = consent.closest("label");
  const enable = form.querySelector("[data-push-enable]");
  const disable = form.querySelector("[data-push-disable]");
  const test = form.querySelector("[data-push-test]");
  const csrf = form.querySelector("[name=csrfmiddlewaretoken]").value;
  let registration;
  let subscription;
  let key;
  let active = false;
  let busy = false;

  function updateControls() {
    const canEnable = key && Notification.permission !== "denied" && !active;
    form.hidden = !active && !canEnable;
    consentLabel.hidden = !canEnable;
    consent.required = Boolean(canEnable);
    enable.hidden = !canEnable;
    enable.disabled = busy || !consent.checked;
    disable.hidden = !active;
    disable.disabled = busy;
    test.hidden = !active || !subscription || Notification.permission === "denied";
    test.disabled = busy;
  }

  async function request(action, data = {}) {
    const response = await fetch(root.dataset.pushUrl, action ? {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
      body: JSON.stringify({ action, ...data }),
    } : { cache: "no-store" });
    if (!response.ok) {
      const error = new Error("Web Push");
      error.status = response.status;
      throw error;
    }
    return response.json();
  }

  function asBytes(value) {
    const padded = value.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(value.length / 4) * 4, "=");
    return Uint8Array.from(atob(padded), (character) => character.charCodeAt(0));
  }

  const denied = "Разрешите уведомления для «Массаж72» в настройках iOS и снова откройте приложение.";
  function showState() {
    if (!key) status.textContent = "Уведомления пока недоступны.";
    else if (Notification.permission === "denied") status.textContent = denied;
    else if (active) status.textContent = "Уведомления включены на этом устройстве.";
    else status.textContent = "Включите уведомления, чтобы получать обновления в кабинете.";
  }

  async function refresh() {
    if (busy) return;
    busy = true;
    updateControls();
    try {
      const state = await request();
      key = state.key ? asBytes(state.key) : null;
      if (key) {
        if (!await worker) throw new Error("Service worker");
        registration = await navigator.serviceWorker.ready;
        subscription = await registration.pushManager.getSubscription();
      }
      active = state.active;
      if (key && active && !subscription && Notification.permission !== "denied") {
        await request("unsubscribe");
        active = false;
      }
      showState();
    } catch {
      status.textContent = "Не удалось проверить уведомления. Обновите страницу.";
    } finally {
      busy = false;
      updateControls();
    }
  }

  consent.addEventListener("change", updateControls);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (busy || !key || !consent.checked) return;
    busy = true;
    updateControls();
    try {
      // Safari requires subscribe() during the tap that grants permission.
      if (!subscription) {
        subscription = await registration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: key,
        });
      }
      const subscriptionKey = subscription.options.applicationServerKey;
      const currentKey = subscriptionKey && new Uint8Array(subscriptionKey);
      if (currentKey && (currentKey.length !== key.length || !key.every((value, index) => currentKey[index] === value))) {
        await subscription.unsubscribe();
        subscription = null;
        status.textContent = "Настройки доставки обновились. Нажмите «Включить уведомления» ещё раз.";
        return;
      }
      await request("subscribe", { consent: true, subscription: subscription.toJSON() });
      active = true;
      consent.checked = false;
      showState();
    } catch (error) {
      if (error.status === 409 && subscription) {
        await subscription.unsubscribe().catch(() => {});
        subscription = null;
      }
      status.textContent = Notification.permission === "denied"
        ? denied
        : "Не удалось включить уведомления. Попробуйте ещё раз.";
    } finally {
      busy = false;
      updateControls();
    }
  });

  disable.addEventListener("click", async () => {
    if (busy || !active) return;
    busy = true;
    updateControls();
    try {
      await request("unsubscribe");
      active = false;
      if (subscription) {
        await subscription.unsubscribe().catch(() => {});
        subscription = null;
      }
      showState();
    } catch {
      status.textContent = "Не удалось отключить уведомления. Попробуйте ещё раз.";
    } finally {
      busy = false;
      updateControls();
    }
  });

  test.addEventListener("click", async () => {
    if (busy || !active) return;
    busy = true;
    updateControls();
    try {
      await request("test");
      status.textContent = "Тест поставлен в очередь. Уведомление обычно приходит в течение минуты.";
    } catch (error) {
      status.textContent = error.status === 429
        ? "Повторить тест можно через минуту."
        : "Не удалось запустить тест. Обновите страницу и попробуйте ещё раз.";
    } finally {
      busy = false;
      updateControls();
    }
  });

  refresh();
  window.addEventListener("pageshow", (event) => {
    if (event.persisted) refresh();
  });
})();
