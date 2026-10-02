// Explicit allowlist: never publish backend, configuration, or customer data.
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const out = path.join(root, 'dist');
fs.mkdirSync(path.join(out, 'static'), { recursive: true });
for (const file of ['app.js', 'style.css']) {
  fs.copyFileSync(path.join(root, 'frontend/static', file), path.join(out, 'static', file));
}
for (const file of ['demo.js', 'demo.css']) {
  fs.copyFileSync(path.join(root, 'frontend/demo', file), path.join(out, 'static', file));
}
const html = fs.readFileSync(path.join(root, 'frontend/index.html'), 'utf8')
  .replace('<title>Weles</title>', '<title>Weles — interaktywne demo pakowania</title>\n  <meta name="description" content="Wypróbuj Weles: zamówienia Allegro, kompletowanie i pakowanie. Interaktywne demo bez konta." />')
  .replaceAll('"/static/', '"./static/')
  .replace('</head>', '  <link rel="stylesheet" href="./static/demo.css" />\n</head>')
  .replace('<script src="./static/app.js">', '<script src="./static/demo.js"></script>\n<script src="./static/app.js">');
fs.writeFileSync(path.join(out, 'index.html'), html);
fs.writeFileSync(path.join(out, '.nojekyll'), '');
console.log('Built GitHub Pages demo in dist/');
