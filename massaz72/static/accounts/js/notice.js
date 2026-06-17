// Авто-скрытие флеш-уведомлений (.account__notice) и очистка query-параметров,
// чтобы сообщение не возвращалось при перезагрузке страницы.
(function () {
  "use strict";

  // Убираем разовые параметры из URL сразу — reload уже будет чистым.
  try {
    var url = new URL(window.location.href);
    var dirty = false;
    ["saved", "password", "reset", "cancel"].forEach(function (key) {
      if (url.searchParams.has(key)) {
        url.searchParams.delete(key);
        dirty = true;
      }
    });
    if (dirty) {
      history.replaceState(null, "", url.pathname + url.search + url.hash);
    }
  } catch (e) {
    /* URL может не поддерживаться — не критично */
  }

  document.addEventListener("DOMContentLoaded", function () {
    var notices = document.querySelectorAll(".account__notice");
    notices.forEach(function (el) {
      setTimeout(function () {
        el.classList.add("account__notice--hide");
        setTimeout(function () {
          el.remove();
        }, 400);
      }, 4000);
    });
  });
})();
