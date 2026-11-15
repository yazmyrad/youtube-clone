// Runs before the first paint, so a page never flashes the other theme. A file rather than an
// inline script, because the CSP allows only scripts from this site. See src/theme.ts.
try {
  var theme = localStorage.getItem("appearance.theme");
  if (theme === "dark" || theme === "light") document.documentElement.dataset.theme = theme;
} catch (error) {
  // Storage blocked: the device's theme it is.
}
