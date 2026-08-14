"""Extract all image references and their surrounding context from all markdown files."""
import os
import re
import json

textbook_dir = os.path.dirname(os.path.abspath(__file__))
results = []

for md_path in sorted([
    os.path.join(dp, f) 
    for dp, _, fs in os.walk(textbook_dir) 
    for f in fs if f.endswith('.md')
]):
    with open(md_path, encoding='utf-8') as f:
        lines = f.readlines()
    
    for i, line in enumerate(lines):
        matches = re.findall(r'!\[([^\]]*)\]\((images/[^)]+)\)', line)
        for alt, img_path in matches:
            # Get context: 3 lines before, 5 lines after
            ctx_before = ''.join(lines[max(0, i-3):i]).strip()
            ctx_after = ''.join(lines[i+1:i+6]).strip()
            results.append({
                'file': os.path.relpath(md_path, textbook_dir),
                'line': i + 1,
                'alt': alt,
                'image_path': img_path,
                'context_before': ctx_before,
                'context_after': ctx_after,
            })

# Categorize
has_figure_caption = 0
has_sublabel = 0
no_context = 0

for r in results:
    ctx = r['context_after']
    # Check for 图X-Y caption
    if re.search(r'图\s*\d+[-—]\d+', ctx):
        has_figure_caption += 1
    # Check for sub-label (a, b, c followed by text)
    elif re.match(r'^[a-z]\s+\S', ctx):
        has_sublabel += 1
    else:
        no_context += 1

print(f"Total image references: {len(results)}")
print(f"  With figure caption (图X-Y): {has_figure_caption}")
print(f"  With sub-label (a/b/c): {has_sublabel}")
print(f"  No clear context: {no_context}")

# Save full data for inspection
with open(os.path.join(textbook_dir, 'image_context.json'), 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print(f"\nFull data saved to image_context.json")
