"""Package the existing approved logo as web icons; do not redraw the artwork."""
from pathlib import Path
from PIL import Image

root = Path(__file__).resolve().parents[1]
source = root / "frontend/assets/images/logo.jpg"
target = root / "frontend/public/icons"
target.mkdir(parents=True, exist_ok=True)
with Image.open(source) as original:
    logo = original.convert("RGB")
    for size in (64, 180, 192, 512):
        logo.resize((size, size), Image.Resampling.LANCZOS).save(target / f"britsmaid-{size}-v1.png")
    mask = Image.new("RGB", (512, 512), "white")
    mask.paste(logo.resize((410, 410), Image.Resampling.LANCZOS), (51, 51))
    mask.save(target / "britsmaid-maskable-512-v1.png")
print("Packaged five PNG icons from the existing Britsmaid logo.")
