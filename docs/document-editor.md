# A4 document editor

## Usage

Open Settings → custom document. Choose uploaded PDF or designed template as the print source. Select a named template, rename and Save to update it; Duplicate creates a new template (including saved draft edits). Delete requires confirmation, and the last template cannot be deleted. The collection supports up to ten templates.

Add text, placeholder, items, logo or line blocks; legacy heading/customer blocks remain supported. Click a block on the A4 canvas or its property header. Drag to move; drag the bottom-right handle to resize. Coordinates and dimensions use millimetres, snap to 1 mm and stay inside the 210 × 297 mm page. Focus a canvas block and use arrows for 1 mm, Shift+arrows for 10 mm, Delete/Backspace to remove. Properties expose font size (8–36 pt), bold, alignment and X/Y/W/H.

Use the field buttons to insert `{{buyer.name}}`, `{{buyer.address}}`, `{{order.id}}`, `{{order.date}}`, or `{{items}}`. Legacy `buyer_name`, `buyer_address`, `order_number`, `date`, `courier`, `pickup_point`, `tracking_number` also work. `order.id` is the internal ID; `order_number` is the Allegro ID. Dates use the current local date. Unknown valid names warn and render an em dash; malformed braces block saving and PDF preview.

The canvas updates immediately using the chosen order or Sample data. User/customer strings are rendered as text, not HTML. PDF preview sends the unsaved draft for a real order without saving; sample data cannot generate a PDF. Canvas preview is approximate: confirm the actual PDF before printing. Fixed boxes clip overflowing content; enlarge the box or reduce font size. PNG/JPEG logos only, up to 2 MB; SVG is rejected. Legacy flow layouts migrate on load, preserving content and defaulting heading to bold. Drafts survive navigation, language changes and in-flight saves.
