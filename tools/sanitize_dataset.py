# tools/sanitize_dataset.py
import os, pathlib
from PIL import Image, ImageOps, ImageFile
ImageFile.LOAD_TRUNCATED_IMAGES = True

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except Exception:
    pass

ROOT = 'static/dataset'
VALID = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tif', '.tiff', '.heic', '.heif'}

for root, _, files in os.walk(ROOT):
    for f in files:
        p = pathlib.Path(root) / f
        if p.suffix.lower() not in VALID:
            continue
        try:
            with Image.open(p) as im:
                im = ImageOps.exif_transpose(im).convert('RGB')
                out = p.with_suffix('.jpg')  # paksa ke JPG
                im.save(out, 'JPEG', quality=92, optimize=True)
                if out != p:
                    p.unlink(missing_ok=True)  # hapus file lama
                print("OK  :", out)
        except Exception as e:
            print("BAD :", p, e)
