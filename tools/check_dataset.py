# tools/check_dataset.py
import os, numpy as np
from PIL import Image, ImageOps

ROOT='static/dataset'
bad=[]

for r,_,files in os.walk(ROOT):
    for f in files:
        p=os.path.join(r,f)
        try:
            with Image.open(p) as im:
                im=ImageOps.exif_transpose(im).convert('RGB')
                arr=np.asarray(im)
                if arr.dtype!=np.uint8 or arr.ndim!=3 or arr.shape[2]!=3:
                    bad.append((p, arr.dtype, arr.shape))
        except Exception as e:
            bad.append((p, str(e), ''))
for b in bad:
    print("BAD:", b)
print("DONE. BAD COUNT:", len(bad))
