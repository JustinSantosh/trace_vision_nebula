import re
from pathlib import Path

app_js = Path("frontend/assets/app.js").read_text(encoding="utf-8")
print("Length of app.js:", len(app_js))

# Find api calls
endpoints = set(re.findall(r'["\'](/api/[^"\']+)["\']', app_js))
print("Endpoints found in app.js:")
for ep in sorted(endpoints):
    print(" -", ep)

