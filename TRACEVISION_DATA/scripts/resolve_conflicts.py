import re
from pathlib import Path

def resolve_file(path_str):
    p = Path(path_str)
    text = p.read_text(encoding="utf-8")
    
    # Pattern to match git conflict markers
    # <<<<<<< HEAD\n(head)\n=======\n(incoming)\n>>>>>>> (hash)\n
    pattern = re.compile(r'<<<<<<< HEAD\r?\n(.*?)\r?\n=======\r?\n(.*?)\r?\n>>>>>>> [a-f0-9]+\r?\n', re.DOTALL)
    
    matches = list(pattern.finditer(text))
    print(f"{path_str}: found {len(matches)} conflicts")
    
    # Replace with incoming (group 2)
    resolved = pattern.sub(r'\2\n', text)
    
    # Check if any conflict markers remain
    if "<<<<<<<" in resolved:
        print(f"WARNING: unresolved markers in {path_str}")
    else:
        print(f"SUCCESS: all markers resolved in {path_str}")
        
    p.write_text(resolved, encoding="utf-8")

resolve_file("frontend/index.html")
resolve_file("frontend/assets/app.js")
resolve_file("frontend/assets/styles.css")

