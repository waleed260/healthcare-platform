// Receives Web Push messages for the clinic workspace and shows a
// privacy-safe notification. The server only ever sends the stored alert
// title/body; no patient data, tokens, or signed URLs travel over push.
self.addEventListener("push", (event) => {
  let payload = { title: "Clinic alert", body: "Open the workspace to review it.", kind: "clinic-alert" };
  try {
    if (event.data) payload = { ...payload, ...event.data.json() };
  } catch {
    // Fall back to the generic message when a payload cannot be parsed.
  }
  event.waitUntil(
    self.registration.showNotification(payload.title, {
      body: payload.body,
      tag: payload.kind || "clinic-alert",
      data: { url: "/operations" },
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = event.notification.data && event.notification.data.url ? event.notification.data.url : "/operations";
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
      for (const client of windows) {
        if (client.url.includes("/operations") && "focus" in client) return client.focus();
      }
      return self.clients.openWindow(target);
    })
  );
});
