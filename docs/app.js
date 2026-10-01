// Set this to the URL of your deployed Pawgress instance, e.g.
// "https://pawgress.onrender.com". Leave it empty to show a placeholder.
var LIVE_APP_URL = "";

(function () {
  var links = document.querySelectorAll("#app-link, #app-link-2");

  if (!LIVE_APP_URL) {
    document.getElementById("app-note").hidden = false;
    links.forEach(function (link) {
      link.classList.remove("btn");
      link.classList.add("btn", "btn-disabled");
    });
    return;
  }

  links.forEach(function (link) {
    link.href = LIVE_APP_URL;
    link.target = "_blank";
    link.rel = "noopener";
  });
})();
