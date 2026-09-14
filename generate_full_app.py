# Build complete index.html
import json

with open("styles.css", "r", encoding="utf-8") as f:
    css = f.read()

# We will generate the complete standalone single-file index.html
print("Read styles.css successfully, length:", len(css))
