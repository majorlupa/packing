// Additional coverage drives the real canvas listeners using the same DOM
// contract as the established editor regression suite (without running it twice).
const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');
const harnessSource = fs.readFileSync('frontend/tests/document-editor.test.cjs', 'utf8').split("test('renders source options")[0];
const { loadEditor, mount, settingsFixture } = new Function('require', harnessSource + '\nreturn { loadEditor, mount, settingsFixture };')(require);
const plain = value => JSON.parse(JSON.stringify(value));
function fixture(blocks, source = 'template') {
  return settingsFixture({templates:[{id:'default',name:'Canvas',blocks}],profiles:{default:{source,active_template_id:'default'}}});
}
function setup(blocks, orders = []) {
  const context = loadEditor();
  const container = mount(context, fixture(blocks), orders);
  return {context, container, editor:context.DocumentEditor};
}
function firstCanvas(container) { return container.querySelector('.editor-canvas-block'); }
function pointer(node, type, x, y, extra = {}) {
  return node.dispatch(type, {pointerId:7, button:0, clientX:x, clientY:y, ...extra});
}

test('template directives and malformed delimiters block saving before a request', () => {
  for (const text of ['{% for x in y %}', '{# comment #}', '{{buyer.name()}}', 'broken}}']) {
    const {context, container} = setup([{type:'text',text}]);
    assert.equal(container.querySelector('.editor-save').disabled,true);
    container.querySelector('.editor-save').click();
    assert.equal(context.apiCalls.length,0);
  }
});

test('legacy migration reserves A4 boxes and preserves explicit geometry and heading bold', () => {
  const {editor} = setup([{type:'heading',text:'Heading'}, {type:'customer'}, {type:'items'}, {type:'line', x:200, y:295, w:30, h:9, bold:false}]);
  const blocks = plain(editor.draft.blocks);
  assert.deepEqual(blocks.map(({x,y,w,h,bold}) => ({x,y,w,h,bold})), [
    {x:18,y:18,w:174,h:18,bold:true}, {x:18,y:42,w:174,h:30,bold:false},
    {x:18,y:78,w:174,h:90,bold:false}, {x:200,y:295,w:10,h:2,bold:false},
  ]);
});

test('pointer dragging snaps to mm, preserves dimensions and clamps at every page edge', () => {
  const {container, editor} = setup([{type:'text',text:'Move',x:18,y:18,w:30,h:20}]);
  const node = firstCanvas(container);
  pointer(node,'pointerdown',10,10);
  assert.equal(node.capturedPointer,7);
  pointer(node,'pointermove',15,17);
  assert.deepEqual(plain(editor.draft.blocks[0]), {type:'text',text:'Move',align:'left',size:12,show_prices:false,image:'',bold:false,x:21,y:22,w:30,h:20});
  pointer(node,'pointermove',10000,10000);
  assert.equal(editor.draft.blocks[0].x,180);
  assert.equal(editor.draft.blocks[0].y,277);
  pointer(node,'pointermove',-10000,-10000);
  assert.equal(editor.draft.blocks[0].x,0);
  assert.equal(editor.draft.blocks[0].y,0);
  pointer(node,'pointerup',0,0);
  const revision = editor.draft.revision;
  pointer(node,'pointermove',500,500);
  assert.equal(editor.draft.revision,revision,'pointerup ends the gesture');
  assert.equal(container.querySelector('.editor-geometry-x').value,'0');
});

test('resize handle snaps, clamps to A4 and pointer cancel stops updates', () => {
  const {container,editor} = setup([{type:'logo',x:190,y:280,w:10,h:10}]);
  const node = firstCanvas(container), resize = node.querySelector('.editor-resize');
  pointer(node,'pointerdown',10,10,{target:resize});
  pointer(node,'pointermove',19,15);
  assert.equal(editor.draft.blocks[0].w,15);
  assert.equal(editor.draft.blocks[0].h,13);
  pointer(node,'pointermove',10000,10000);
  assert.equal(editor.draft.blocks[0].w,20);
  assert.equal(editor.draft.blocks[0].h,17);
  pointer(node,'pointermove',-10000,-10000);
  assert.equal(editor.draft.blocks[0].w,1);
  assert.equal(editor.draft.blocks[0].h,1);
  pointer(node,'pointercancel',0,0);
  pointer(node,'pointermove',20,20);
  assert.equal(editor.draft.blocks[0].w,1);
});

test('wrong pointer and non-primary button cannot mutate geometry', () => {
  const {container,editor} = setup([{type:'line',x:12,y:13,w:40,h:1}]);
  const node = firstCanvas(container);
  pointer(node,'pointerdown',0,0,{button:2});
  pointer(node,'pointermove',30,30);
  assert.equal(editor.draft.blocks[0].x,12);
  pointer(node,'pointerdown',0,0);
  pointer(node,'pointermove',30,30,{pointerId:8});
  assert.equal(editor.draft.blocks[0].x,12);
});

test('keyboard handlers nudge and delete canvas blocks, never input content', () => {
  const {container,editor} = setup([{type:'text',text:'Keyboard',x:10,y:10,w:30,h:20},{type:'line'}]);
  const node = firstCanvas(container);
  node.dispatch('keydown',{key:'ArrowRight'});
  assert.equal(editor.draft.blocks[0].x,11);
  node.dispatch('keydown',{key:'ArrowDown',shiftKey:true});
  assert.equal(editor.draft.blocks[0].y,20);
  const input = container.querySelector('.editor-block-text');
  node.dispatch('keydown',{key:'Delete',target:input});
  node.dispatch('keydown',{key:'ArrowUp',target:input});
  assert.equal(editor.draft.blocks.length,2);
  assert.equal(editor.draft.blocks[0].y,20);
  node.dispatch('keydown',{key:'Delete'});
  assert.equal(editor.draft.blocks.length,1);
  assert.equal(editor.draft.blocks[0].type,'line');
});

test('real geometry, font, bold and alignment controls update the save payload', () => {
  const {context,container,editor} = setup([{type:'text',text:'Properties'}]);
  for (const [key,value] of Object.entries({x:'209.8',y:'296.9',w:'-5',h:'1000'})) {
    const input = container.querySelector('.editor-geometry-' + key); input.value=value; input.dispatch('input');
  }
  const size = container.querySelector('.editor-block-size'); size.value='99'; size.dispatch('input');
  const bold = container.querySelector('.editor-block-bold'); bold.checked=true; bold.dispatch('change');
  const align = container.querySelector('.editor-block-align'); align.value='right'; align.dispatch('change');
  container.querySelector('.editor-save').click();
  const block = JSON.parse(context.apiCalls[0].options.body).template.blocks[0];
  assert.equal(block.x,209); assert.equal(block.y,296); assert.equal(block.w,1); assert.equal(block.h,1);
  assert.equal(block.size,36); assert.equal(block.bold,true); assert.equal(block.align,'right');
  assert.equal(editor.draft.blocks[0].text,'Properties');
});

test('dotted picker resolves selected order in one pass and warns without blocking unknown tokens', () => {
  const hostile = '<img src=x onerror=alert(1)> {{order.id}}';
  const {container,editor} = setup([{type:'placeholder',text:'{{buyer.name}} / {{buyer_name}} / {{order.id}} / {{missing}} / {{items}}'}], [{id:'safe-order',buyer_name:hostile,items:[{name:'<script>evil</script>',quantity:2}]}]);
  const content = container.querySelector('.editor-canvas-content');
  assert.equal(content.textContent,hostile + ' / ' + hostile + ' / safe-order / — / <script>evil</script> × 2');
  assert.equal(content.children.length,0,'customer data is text, never markup');
  assert.match(container.querySelector('.editor-warnings').textContent,/missing/);
  assert.equal(container.querySelector('.editor-save').disabled,false);
  const textarea = container.querySelector('.editor-block-text'); textarea.value=''; textarea.selectionStart=textarea.selectionEnd=0;
  container.querySelector('.editor-token[data-token="buyer.address"]').click();
  assert.equal(editor.draft.blocks[0].text,'{{buyer.address}}');
  assert.equal(container.querySelector('.editor-warnings').textContent,'');
});

test('sample preview is immediate offline and explicit sample selection survives redraw', () => {
  const {context,container,editor} = setup([{type:'text',text:'{{buyer.name}}'}],[{id:'order',buyer_name:'Real buyer'}]);
  assert.equal(container.querySelector('.editor-canvas-content').textContent,'Real buyer');
  const select = container.querySelector('.editor-preview-order'); select.value=''; select.dispatch('change');
  assert.equal(container.querySelector('.editor-canvas-content').textContent,'Anna Kowalska');
  container.querySelector('.editor-add-block').click();
  assert.equal(editor.draft.previewOrderId,'');
  assert.equal(container.querySelector('.editor-preview-order').value,'');
  assert.equal(context.apiCalls.length,0);
});

test('selected order changes immediately update escaped text and items', () => {
  const {container} = setup([{type:'customer'},{type:'items',show_prices:true}], [
    {id:'a',buyer_name:'Alice',buyer_address:'First\nAddress',items:[{name:'A',quantity:1,unit_price:2}]},
    {id:'b',buyer_name:'<b>Bob</b>',buyer_address:'Second\nAddress',items:[{name:'<img>x',quantity:3,unit_price:4.5}]},
  ]);
  const select = container.querySelector('.editor-preview-order'); select.value='b'; select.dispatch('change');
  const content = container.querySelectorAll('.editor-canvas-content');
  assert.equal(content[0].textContent,'<b>Bob</b>\nSecond\nAddress');
  assert.equal(content[0].children.length,0);
  assert.match(content[1].textContent,/<img>x/);
  assert.ok(content[1].querySelector('table'),'items use table layout, not a text approximation');
  assert.deepEqual(content[1].querySelectorAll('td').map(cell => cell.textContent), ['<img>x','3','4.50 zł','13.50 zł','Razem','13.50 zł']);
  assert.equal(content[1].querySelectorAll('img').length,0,'item names cannot introduce markup');
});

test('missing prices render dashes and suppress the total, sample uses backend unit_price', () => {
  const {container} = setup([{type:'items',show_prices:true}], [{id:'a',items:[{name:'No price',quantity:1,unit_price:null}]}]);
  let content = container.querySelector('.editor-canvas-content');
  assert.deepEqual(content.querySelectorAll('td').map(cell => cell.textContent),['No price','1','—','—']);
  const select = container.querySelector('.editor-preview-order'); select.value=''; select.dispatch('change');
  content = container.querySelector('.editor-canvas-content');
  assert.deepEqual(content.querySelectorAll('td').map(cell => cell.textContent), ['Sample item','2','19.99 zł','39.98 zł','Razem','39.98 zł']);
});

test('canvas refuses remote, SVG and malformed loaded logo URLs', () => {
  for (const image of ['https://example.org/logo.png','data:image/svg+xml;base64,AAAA','data:image/png;base64,AAAA" onerror="evil']) {
    const {container} = setup([{type:'logo',image}]);
    const img = container.querySelector('.editor-canvas-content').querySelector('img');
    assert.equal(img.getAttribute('src'),null);
  }
});

test('unknown placeholder warnings translate in place without translating authored text', () => {
  const {context,container} = setup([{type:'text',text:'{{buyer.unknown}}'}]);
  context.setLanguage('en',{root:container});
  assert.match(container.querySelector('.editor-warnings').textContent,/Unknown/);
  assert.equal(container.querySelector('.editor-block-text').value,'{{buyer.unknown}}');
});

test('delayed logo read after remount updates the current canvas, removed blocks are ignored', () => {
  const readers = [];
  const context = loadEditor({FileReader:class {readAsDataURL() {readers.push(this);}}});
  let container = mount(context,fixture([{type:'logo'}]));
  const input = container.querySelector('.editor-logo-file'); input.files=[{type:'image/png',size:10}]; input.dispatch('change');
  container = mount(context,fixture([{type:'logo'}]));
  readers[0].result='data:image/png;base64,iVBORw0KGgo='; readers[0].onload();
  assert.equal(context.DocumentEditor.draft.blocks[0].image,readers[0].result);
  assert.equal(container.querySelector('.editor-canvas-content').querySelector('img').getAttribute('src'),readers[0].result);
  const second = container.querySelector('.editor-logo-file'); second.files=[{type:'image/png',size:10}]; second.dispatch('change');
  container.querySelector('.editor-block-remove').click();
  readers[1].result='data:image/png;base64,AAAA'; readers[1].onload();
  assert.equal(context.DocumentEditor.draft.blocks.length,0);
});
