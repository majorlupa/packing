const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const test = require('node:test');
const harnessSource = fs.readFileSync('frontend/tests/document-editor.test.cjs', 'utf8').split("test('renders source options")[0];
const { loadEditor, settingsFixture, Dom } = new Function('require', harnessSource + '\nreturn { loadEditor, settingsFixture, Dom };')(require);

// Parse the settings markup into the existing editor DOM harness so assertions
// check ancestry and the real mount target, not just matching source strings.
class SettingsPanel extends Dom {
  set innerHTML(html) {
    this.children = [];
    const stack = [this];
    for (const token of html.matchAll(/<\/?([\w-]+)\b([^>]*)>|([^<]+)/g)) {
      if (token[3]) {
        if (token[3].trim()) {
          const text = new Dom('span');
          text.textContent = token[3];
          stack.at(-1).appendChild(text);
        }
      } else if (token[0].startsWith('</')) {
        stack.pop();
      } else {
        const node = new Dom(token[1]);
        for (const attr of token[2].matchAll(/([\w-]+)="([^"]*)"/g)) {
          node.setAttribute(attr[1], attr[2]);
          if (attr[1] === 'class') node.classList.add(...attr[2].split(/\s+/));
        }
        stack.at(-1).appendChild(node);
        if (!['input', 'br', 'hr', 'img'].includes(token[1])) stack.push(node);
      }
    }
  }
}

async function renderSettings(language = 'pl') {
  const context = loadEditor();
  const panel = new SettingsPanel();
  context.panel = panel;
  context.fixture = settingsFixture({ templates: [{ id: 'default', name: 'My template', blocks: [{ type: 'text', text: 'Original' }] }] });
  vm.runInContext(`
    setLanguage('${language}');
    api = async path => path === '/print/document-settings' ? fixture : {};
  `, context);
  await vm.runInContext('renderSettingsDocuments(panel)', context);
  return { context, panel };
}

for (const [language, title, linkLabel, sideLabel] of [
  ['pl', 'Edytor dokumentu A4', 'Przejdź do edytora dokumentu', 'Bloki i pola dynamiczne'],
  ['en', 'A4 document editor', 'Go to document editor', 'Blocks and placeholders'],
]) {
  test(`Settings mounts one full-width editor card with localized controls (${language})`, async () => {
    const { panel } = await renderSettings(language);
    const card = panel.querySelector('#document-editor-card');
    assert.equal(card.parentNode, panel, 'card must not be inside a capped settings section');
    assert.ok(card.classList.contains('settings-editor-card'));
    assert.equal(card.getAttribute('aria-labelledby'), 'document-editor-title');
    assert.equal(card.querySelector('#document-editor-title').textContent, title);
    assert.equal(panel.querySelectorAll('.document-editor').length, 1);
    assert.equal(panel.querySelectorAll('#document-editor').length, 1);
    assert.ok(card.querySelector('.editor-canvas'));
    assert.equal(card.querySelector('.editor-side-panel').getAttribute('aria-label'), sideLabel);
    assert.ok(card.querySelector('.editor-side-panel .editor-add-block'));
    assert.ok(card.querySelector('.editor-side-panel .editor-token'));
    for (const control of ['.editor-template-import', '.editor-template-export', '.editor-template-export-all', '.editor-import-conflict']) {
      assert.ok(card.querySelector(control), control);
    }
    const link = panel.querySelector('#open-document-editor');
    assert.equal(link.textContent, linkLabel);
    assert.equal(link.getAttribute('href'), '#document-editor-card');
    assert.equal(link.parentNode.querySelector('.document-editor'), null, 'old location contains only navigation');
  });
}

test('editor shortcut focuses and scrolls to the card without remounting or losing edits', async () => {
  const { context, panel } = await renderSettings();
  const card = panel.querySelector('#document-editor-card');
  const editor = card.querySelector('.document-editor');
  const textarea = editor.querySelector('.editor-block-text');
  textarea.value = 'Unsaved edit';
  textarea.dispatch('input');
  let focused = false;
  let scrolled = false;
  let prevented = false;
  card.focus = options => { focused = options.preventScroll; };
  card.scrollIntoView = options => { scrolled = options.block === 'start'; };
  panel.querySelector('#open-document-editor').dispatch('click', { preventDefault() { prevented = true; } });
  assert.ok(focused && scrolled && prevented);
  assert.equal(card.querySelector('.document-editor'), editor);
  assert.equal(vm.runInContext('DocumentEditor.draft.blocks[0].text', context), 'Unsaved edit');
});

test('editor layout fills the card, preserves A4 and stacks canvas before the side panel', async () => {
  const { panel } = await renderSettings();
  const workspace = panel.querySelector('.editor-workspace');
  assert.ok(workspace.children[0].classList.contains('editor-canvas-wrap'));
  assert.ok(workspace.children[1].classList.contains('editor-side-panel'));
  const css = fs.readFileSync('frontend/static/document-editor.css', 'utf8');
  assert.match(css, /\.settings-editor-card\s*\{[^}]*width: 100%;[^}]*max-width: none;/);
  assert.match(css, /\.editor-canvas\s*\{[^}]*width: 100%;[^}]*aspect-ratio: 210 \/ 297;/);
  assert.match(css, /@container \(max-width: 760px\)\s*\{\s*\.editor-workspace\s*\{\s*grid-template-columns: minmax\(0, 1fr\);/);
  assert.match(css, /@media \(max-width: 850px\)\s*\{\s*\.editor-workspace\s*\{\s*grid-template-columns: minmax\(0, 1fr\);/);
  assert.doesNotMatch(css, /max-width: 600px/);
});
