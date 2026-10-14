// Theme before first paint (CSP allows only same-origin scripts, so this is not inline).
// A campaign in the #campaigns block may carry "theme": BAM8 = "academy" (the pngoungacademy.com look, academy.css).
(function () {
  try {
    var cfg = JSON.parse(document.getElementById('campaigns').textContent);
    var want = (new URLSearchParams(location.search).get('c') || '').trim().toUpperCase();
    var id = Object.keys(cfg.campaigns).filter(function (k) { return k.toUpperCase() === want; })[0] || cfg.default;
    var theme = cfg.campaigns[id] && cfg.campaigns[id].theme;
    if (theme) document.documentElement.setAttribute('data-theme', theme);
  } catch (e) { /* default theme */ }
})();
