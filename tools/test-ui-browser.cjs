// Run with PLAYWRIGHT_MODULE pointing to an externally installed Playwright.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { test, before, after } = require('node:test');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
let browser;
before(async () => { browser = await chromium.launch({ headless: true }); });
after(async () => { if (browser) await browser.close(); });
async function pageFor(html) {
  const page = await browser.newPage();
  await page.setContent(`<style>${fs.readFileSync('frontend/static/style.css', 'utf8')}\n${fs.readFileSync('frontend/static/document-editor.css', 'utf8')}</style>${html}`);
  return page;
}
test('preview action has a visible border', async () => {
  const page = await pageFor('<div class="editor-actions"><button class="editor-preview">Preview</button></div>');
  try {
    assert.notEqual(await page.locator('button').evaluate(node => getComputedStyle(node).borderTopColor), 'rgba(0, 0, 0, 0)');
  } finally { await page.close(); }
});
test('filled button hover colors retain AA contrast', async () => {
  const page = await pageFor('<button class="btn btn-primary">Primary</button><button class="btn btn-done">Done</button>');
  try {
    for (const selector of ['.btn-primary', '.btn-done']) {
      await page.locator(selector).hover();
      await page.waitForTimeout(200);
      const ratio = await page.locator(selector).evaluate(node => {
        const luminance = color => {
          const channels = color.match(/[\d.]+/g).slice(0, 3).map(Number).map(v => v / 255).map(v => v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
          return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722;
        };
        const style = getComputedStyle(node), a = luminance(style.color), b = luminance(style.backgroundColor);
        return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
      });
      assert.ok(ratio >= 4.5, `${selector}: ${ratio}`);
    }
  } finally { await page.close(); }
});
test('A4 focus outline stays inside the clipped page', async () => {
  const page = await pageFor('<div class="editor-canvas"><div class="editor-canvas-block" tabindex="0" style="left:0;top:0;width:100%;height:20px">Text</div></div>');
  try {
    await page.keyboard.press('Tab');
    const style = await page.locator('.editor-canvas-block').evaluate(node => ({offset:parseFloat(getComputedStyle(node).outlineOffset), width:parseFloat(getComputedStyle(node).outlineWidth)}));
    assert.ok(style.offset <= -style.width);
  } finally { await page.close(); }
});
