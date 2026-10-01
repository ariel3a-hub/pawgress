(function () {
  // Ask before running destructive forms (leaving a group, deleting a dog...).
  document.addEventListener('submit', function (event) {
    var form = event.target.closest('form[data-confirm]');
    if (form && !window.confirm(form.dataset.confirm)) {
      event.preventDefault();
    }
  });

  // Keep the notification badge in sync without reloading the page.
  var badge = document.querySelector('.bell .badge');
  var bell = document.querySelector('.bell');

  function refreshBadge() {
    if (!bell || !window.fetch) return;
    fetch('/api/notifications/unread-count', { credentials: 'same-origin' })
      .then(function (response) { return response.ok ? response.json() : null; })
      .then(function (data) {
        if (!data) return;
        if (data.count > 0) {
          if (!badge) {
            badge = document.createElement('span');
            badge.className = 'badge';
            bell.appendChild(badge);
          }
          badge.textContent = data.count;
        } else if (badge) {
          badge.remove();
          badge = null;
        }
      })
      .catch(function () { /* offline: try again on the next tick */ });
  }

  if (bell) setInterval(refreshBadge, 30000);
})();