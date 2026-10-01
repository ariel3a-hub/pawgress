self.addEventListener('install', function (event) {
  event.waitUntil(self.skipWaiting());
});

self.addEventListener('activate', function (event) {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('push', function (event) {
  var payload = { title: 'Pawgress', body: 'You have a new update.', url: '/notifications' };

  if (event.data) {
    try {
      payload = Object.assign(payload, event.data.json());
    } catch (error) {
      payload.body = event.data.text();
    }
  }

  event.waitUntil(
    self.registration.showNotification(payload.title, {
      body: payload.body,
      icon: '/static/icon-192.png',
      badge: '/static/icon-192.png',
      data: { url: payload.url },
      tag: payload.title
    })
  );
});

self.addEventListener('notificationclick', function (event) {
  event.notification.close();
  var target = (event.notification.data && event.notification.data.url) || '/notifications';

  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (clientList) {
      for (var index = 0; index < clientList.length; index += 1) {
        if (clientList[index].url.indexOf(self.location.origin) === 0) {
          clientList[index].navigate(target);
          return clientList[index].focus();
        }
      }
      return self.clients.openWindow(target);
    })
  );
});