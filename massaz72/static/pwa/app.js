(() => {
  function reminderPaused(preference) {
    try {
      return Number(localStorage.getItem(preference)) > Date.now();
    } catch {
      return false;
    }
  }

  function pauseReminder(preference, days) {
    try {
      localStorage.setItem(preference, String(Date.now() + days * 24 * 60 * 60 * 1000));
    } catch {
      // The dismissal still applies to the current page.
    }
  }

  function setupInstallPromotion(isAppleMobile, standalone) {
    const promotion = document.querySelector("[data-pwa-install]");
    if (!promotion || standalone || !window.isSecureContext
        || (!isAppleMobile && !/Android/.test(navigator.userAgent))) return;

    const dialog = promotion.querySelector("dialog");
    if (typeof dialog.showModal !== "function") return;

    const preference = "massaz_pwa_install_hidden_until";
    if (reminderPaused(preference)) return;

    const nativeInstall = promotion.querySelector("[data-pwa-install-native]");
    let installEvent;

    function hidePromotion() {
      if (dialog.open) dialog.close();
      promotion.hidden = true;
      pauseReminder(preference, 30);
    }

    promotion.querySelector(isAppleMobile ? "[data-pwa-ios]" : "[data-pwa-android]").hidden = false;
    promotion.querySelector("[data-pwa-install-open]").addEventListener("click", () => dialog.showModal());
    promotion.querySelector("[data-pwa-install-close]").addEventListener("click", () => dialog.close());
    promotion.querySelector("[data-pwa-install-dismiss]").addEventListener("click", hidePromotion);
    promotion.hidden = false;

    if (!isAppleMobile) {
      window.addEventListener("beforeinstallprompt", (event) => {
        event.preventDefault();
        installEvent = event;
        nativeInstall.hidden = false;
      });
      window.addEventListener("appinstalled", hidePromotion);
      nativeInstall.addEventListener("click", async () => {
        const prompt = installEvent;
        if (!prompt) return;
        installEvent = undefined;
        nativeInstall.hidden = true;
        try {
          await prompt.prompt();
          const choice = await prompt.userChoice;
          if (choice.outcome === "accepted") hidePromotion();
        } catch {
          // The manual Chrome instructions remain available.
        }
      });
    }
  }

  const script = document.currentScript;
  const root = document.querySelector("[data-push-url]");
  const section = root?.closest("[data-push-section]");
  const pushPromo = document.querySelector("[data-push-promotion]");
  const pushDialog = document.querySelector("[data-push-login-dialog]");
  const isIPad = /iPad/.test(navigator.userAgent)
    || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  const isAppleMobile = isIPad || /iPhone|iPod/.test(navigator.userAgent);
  const standalone = navigator.standalone === true || matchMedia("(display-mode: standalone)").matches;
  setupInstallPromotion(isAppleMobile, standalone);
  const worker = window.isSecureContext && "serviceWorker" in navigator
    ? navigator.serviceWorker.register(script.dataset.worker, { updateViaCache: "none" }).catch(() => null)
    : null;
  const supportsPush = worker && "Notification" in window && "PushManager" in window;
  const loginMarker = "massaz_push_login_at";
  let openAfterLogin = false;
  if (isAppleMobile && standalone && supportsPush) {
    document.querySelector("[data-push-login-form]")?.addEventListener("submit", () => {
      try {
        sessionStorage.setItem(loginMarker, String(Date.now()));
      } catch {
        // The inline offer is still available without session storage.
      }
    });
    if (pushPromo && root) {
      try {
        openAfterLogin = Date.now() - Number(sessionStorage.getItem(loginMarker)) < 120000;
        sessionStorage.removeItem(loginMarker);
      } catch {
        // Keep the offer inline if session storage is unavailable.
      }
    }
  }
  let active = false;
  let dismissPushPromo;
  let later;
  if (pushPromo) {
    const preference = "massaz_push_promo_hidden_until";
    if (!isAppleMobile || !standalone || !supportsPush || Notification.permission === "denied"
        || reminderPaused(preference)) return;

    later = pushPromo.querySelector("[data-push-later]");
    dismissPushPromo = () => {
      pushPromo.hidden = true;
      if (!active) pauseReminder(preference, 7);
      dismissPushPromo = undefined;
      if (pushDialog?.open) pushDialog.close();
    };
    later.addEventListener("click", () => dismissPushPromo?.());
    pushDialog?.addEventListener("close", () => dismissPushPromo?.());
    if (!root) pushPromo.hidden = false;
  }
  if (!root || !isAppleMobile) return;

  if (!pushPromo) {
    root.hidden = false;
    section.hidden = false;
  }
  const status = root.querySelector("[data-push-status]");
  if (!standalone) {
    status.textContent = "В Safari нажмите «Поделиться» → «На экран “Домой”». Затем откройте приложение с экрана «Домой» и вернитесь сюда.";
    return;
  }
  if (!supportsPush) {
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
  let configured = false;
  let busy = false;

  function updateControls() {
    const canEnable = registration && key && Notification.permission !== "denied" && !active;
    form.hidden = !active && !canEnable;
    consentLabel.hidden = !canEnable;
    consent.required = Boolean(canEnable);
    enable.hidden = !canEnable;
    enable.disabled = busy || !consent.checked;
    disable.hidden = !active;
    disable.disabled = busy;
    test.hidden = !active || !subscription || Notification.permission === "denied";
    test.disabled = busy;
    if (later) {
      later.hidden = active && !pushDialog?.open;
      later.textContent = active ? "Готово" : "Позже";
    }
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
    if (!configured) status.textContent = "Сервер пока не настроен для отправки уведомлений.";
    else if (!key) status.textContent = "Уведомления доступны клиентам с кабинетом, активным специалистам и сотрудникам с доступом к заявкам или запросам на удаление ПД.";
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
      configured = state.configured;
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
      if (pushPromo && dismissPushPromo && !pushDialog?.open) {
        pushPromo.hidden = !key || Notification.permission === "denied" || active;
        root.hidden = pushPromo.hidden;
        if (!pushPromo.hidden && openAfterLogin && typeof pushDialog?.showModal === "function") {
          openAfterLogin = false;
          pushDialog.append(pushPromo);
          pushDialog.showModal();
          pushDialog.querySelector("h2").focus();
        }
      }
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
      await request("subscribe", { consent: true, device: isIPad ? "ipad" : "iphone", subscription: subscription.toJSON() });
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
      dismissPushPromo?.();
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
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") refresh();
  });
})();
