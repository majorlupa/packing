# Weles interactive demo

Development branch: `demo/github-pages`, based on `beta`.

The demo reuses the production HTML, CSS, and queue UI. `frontend/demo/demo.js`
provides fictional orders and an in-memory API, plus optional Polish onboarding.
No credentials, customer data, backend, or Allegro connection are used. Reloading
resets all orders; dismissing the welcome screen is remembered for the current tab.
The guide can be skipped, reopened, or restarted from the header. Sample PDFs are
watermarked and are not valid shipping labels or accounting documents.
The Paczkomat InPost category uses per-order A/B/C parcel choices instead of
dimensions and weight. Choices survive queue navigation within the demo session
and appear on sample PDFs; changing the size invalidates the previous sample
label. The demo stores `delivery_type: inpost_locker` and `parcel_size` for a future
API integration. Live carrier integration is not implemented.

Custom PDF uploads are unavailable in the demo and show an explanatory message.

## Preview

```sh
node --test frontend/tests/*.test.cjs
node tools/build-demo.cjs
python3 -m http.server 8080 --directory dist
```

Open http://localhost:8080. The build uses relative asset URLs, so it also works
at a GitHub Pages project path such as `/packing/`. Only the files explicitly
listed in `tools/build-demo.cjs` are copied into `dist/`. Build into a clean
checkout for deployment; do not place unrelated files in `dist/`.

For the browser regression test, install Playwright and its Chromium browser in
your test environment, then run `node tools/test-demo-browser.cjs` after building.
If Playwright is installed elsewhere, set `PLAYWRIGHT_MODULE` to its absolute
module path. The test starts a temporary local server and checks the complete
workflow, sample PDF, onboarding start/skip/Escape/restart, mobile layout, nested
Pages paths, and absence of backend requests.

## Publish

The repository is public, allowing GitHub Pages on GitHub Free. The deployed
artifact contains only the static demo, regardless of what else is in the source
repository.

For Pages in this repository:

1. Enable **Settings → Pages → Source → GitHub Actions**.
2. Push `demo/github-pages`. The `Demo on GitHub Pages` workflow tests, builds,
   and deploys only `dist/` using the `github-pages` environment.
3. Allow that branch in the environment deployment rules, if restricted.
4. Use the URL reported by the deployment job. Expected project URL:
   `https://majorlupa.github.io/packing/`.

The workflow automatically publishes only `demo/github-pages`; if the demo is
merged into `beta`, update its branch filter accordingly. A `gh-pages` branch is
not needed with the Actions deployment.

GitHub documentation: https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages
