{% load static %}"use strict";

const messages = {
  new_booking: ["Новая заявка ждёт обработки.", "{% url 'cabinet:booking_requests' %}"],
  new_booking_admin: ["Новая заявка ждёт обработки.", "{% url 'admin:booking_bookingrequest_changelist' %}"],
  booking_confirmed: ["Статус заявки изменился. Откройте личный кабинет.", "{% url 'accounts:dashboard' %}"],
  booking_declined: ["Статус заявки изменился. Откройте личный кабинет.", "{% url 'accounts:dashboard' %}"],
  test: ["Уведомления на этом устройстве работают.", "/"],
};

self.addEventListener("push", (event) => {
  let kind;
  try {
    kind = event.data?.json()?.kind;
  } catch {
    // Apple expects a visible notification even when the payload is unreadable.
  }
  const [body, path] = typeof kind === "string" && Object.hasOwn(messages, kind)
    ? messages[kind]
    : ["Откройте приложение, чтобы посмотреть обновления.", "/"];
  event.waitUntil(self.registration.showNotification("Массаж72", {
    body,
    icon: "{% static 'favicon/web-app-manifest-192x192.png' %}",
    data: { path },
  }));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const path = event.notification.data?.path;
  const allowed = Object.values(messages).some((message) => message[1] === path);
  const target = new URL(allowed ? path : "/", self.location.origin).href;
  event.waitUntil((async () => {
    const windows = await clients.matchAll({ type: "window", includeUncontrolled: true });
    const window = windows.find((client) => client.url === target);
    return window ? window.focus() : clients.openWindow(target);
  })());
});
