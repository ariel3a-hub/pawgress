(function () {
  var state = document.getElementById('push-state');
  var toggle = document.getElementById('web-push-toggle');
  if (!state || !toggle) return;

  function setState(message, kind) {
    state.textContent = message;
    state.className = 'push-state' + (kind ? ' ' + kind : '');
  }

  if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
    setState('This browser cannot show system notifications.', 'warn');
    return;
  }

  if (Notification.permission === 'denied') {
    setState('Notifications are blocked in your browser settings.', 'warn');
    toggle.disabled = true;
    return;
  }

  function urlBase64ToUint8Array(base64String) {
    var padding = '='.repeat((4 - (base64String.length % 4)) % 4);
    var base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
    var raw = window.atob(base64);
    var output = new Uint8Array(raw.length);
    for (var index = 0; index < raw.length; index += 1) {
      output[index] = raw.charCodeAt(index);
    }
    return output;
  }

  navigator.serviceWorker.register('/sw.js').then(function () {
    return fetch('/api/push/key', { credentials: 'same-origin' });
  }).then(function (response) {
    return response.json();
  }).then(function (data) {
    return navigator.serviceWorker.ready.then(function (registration) {
      return registration.pushManager.getSubscription().then(function (existing) {
        return existing || registration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: urlBase64ToUint8Array(data.public_key)
        });
      });
    });
  }).then(function (subscription) {
    return fetch('/api/push/subscribe', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(subscription.toJSON())
    });
  }).then(function () {
    setState('Browser notifications are on for this device.', 'ok');
  }).catch(function (error) {
    setState('Could not enable browser notifications yet.', 'warn');
    console.warn('Push setup failed:', error);
  });

  toggle.addEventListener('change', function () {
    if (!toggle.checked) {
      navigator.serviceWorker.ready.then(function (registration) {
        return registration.pushManager.getSubscription();
      }).then(function (subscription) {
        if (!subscription) return null;
        return fetch('/api/push/unsubscribe', {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(subscription.toJSON())
        }).then(function () { return subscription.unsubscribe(); });
      });
      setState('Browser notifications are off for this device.');
    }
  });
})();