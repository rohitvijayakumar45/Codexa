"""Renders SVG to ultra-high-resolution 4K/8K PNG using Playwright Chromium."""

from pathlib import Path
from playwright.sync_api import sync_playwright

def render():
    svg_path = Path("docs/codexa_e2e_request_lifecycle.svg").resolve()
    if not svg_path.exists():
        raise FileNotFoundError(f"SVG not found at {svg_path}")
        
    svg_content = svg_path.read_text(encoding="utf-8")
    
    # Wrap in clean dark background HTML
    html_content = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{
    margin: 0;
    padding: 40px;
    background-color: #0f172a;
    display: flex;
    justify-content: center;
    align-items: center;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  }}
  #container {{
    width: 100%;
    max-width: 3200px;
    background: #0f172a;
    border-radius: 16px;
    box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
  }}
  svg {{
    width: 100%;
    height: auto;
    display: block;
  }}
</style>
</head>
<body>
  <div id="container">
    {svg_content}
  </div>
</body>
</html>
"""
    temp_html = Path("docs/temp_diagram.html").resolve()
    temp_html.write_text(html_content, encoding="utf-8")
    
    output_png = Path("docs/codexa_e2e_request_lifecycle.png").resolve()
    artifact_dir = Path(r"C:\Users\rohit\.gemini\antigravity\brain\012b28d2-3e87-4aac-a4e4-f7aed6be8f6e")
    
    with sync_playwright() as p:
        browser = p.chromium.launch()
        # 3400x2400 viewport with 2x device scale factor = 6800x4800 ultra-high definition!
        page = browser.new_page(
            viewport={"width": 3200, "height": 2200},
            device_scale_factor=2
        )
        page.goto(temp_html.as_uri())
        page.wait_for_timeout(1000)
        
        container = page.locator("#container")
        container.screenshot(path=str(output_png))
        print(f"Rendered Ultra-High-Res PNG: {output_png} ({output_png.stat().st_size:,} bytes)")
        
        if artifact_dir.exists():
            artifact_png = artifact_dir / "codexa_e2e_request_lifecycle.png"
            artifact_png.write_bytes(output_png.read_bytes())
            
            artifact_svg = artifact_dir / "codexa_e2e_request_lifecycle.svg"
            artifact_svg.write_bytes(svg_path.read_bytes())
            print(f"Copied to artifacts: {artifact_png}")
            
        browser.close()
        
    temp_html.unlink(missing_ok=True)
    print("Complete!")

if __name__ == "__main__":
    render()
