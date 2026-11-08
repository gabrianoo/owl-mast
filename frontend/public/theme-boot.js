// Applies a saved explicit theme before first paint so the override never flashes (DESIGN.md:
// follow the device theme initially, allow an explicit user override). Reading fails closed to the
// system theme when storage is unavailable. Kept external so the image's CSP can forbid inline scripts.
(function () {
  try {
    var saved = window.localStorage.getItem('owlmast.theme');
    if (saved === 'light' || saved === 'dark') {
      document.documentElement.setAttribute('data-owl-theme', saved);
    }
  } catch {
    // storage unavailable: follow the device theme
  }
})();
