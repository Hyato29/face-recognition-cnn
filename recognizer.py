# recognizer.py — versi stabil (Windows-friendly)
print("[DEBUG] recognizer loaded from:", __file__)

import os
import cv2
import numpy as np
import face_recognition
from PIL import Image, ImageOps, ImageFile

ImageFile.LOAD_TRUNCATED_IMAGES = True

# Opsional: dukung HEIC/HEIF (foto iPhone). Abaikan jika tidak terpasang.
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except Exception:
    pass

# ====== Konfigurasi ======
FACE_RECOGNITION_THRESHOLD = 0.55
MAX_DETECT_WIDTH = 1600          # perkecil gambar lebar > 1600px sebelum deteksi
UPSAMPLE_HOG = 1                 # 0/1 biasanya cukup
USE_CNN_FALLBACK = True          # coba CNN jika HOG gagal

# ====== State ======
KNOWN_ENCODINGS = []
KNOWN_NAMES = []
FACES_LOADED = False


# ---------- Utilitas gambar ----------
def _coerce_rgb_uint8_c_writeable(img: np.ndarray) -> np.ndarray:
    """
    Paksa array jadi RGB uint8 3-channel, C-contiguous dan writeable.
    """
    if img.dtype != np.uint8:
        img = img.astype(np.uint8, copy=False)

    # Pastikan 3-channel
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
    elif img.ndim == 3 and img.shape[2] == 4:
        img = cv2.cvtColor(img, cv2.COLOR_RGBA2RGB)
    elif img.ndim == 3 and img.shape[2] != 3:
        raise ValueError(f"Channel tidak didukung: shape={img.shape}")

    # Paksa C-contiguous + writeable
    img = np.require(img, dtype=np.uint8, requirements=['C', 'W'])
    if (not img.flags['C_CONTIGUOUS']) or (not img.flags['WRITEABLE']):
        img = np.array(img, dtype=np.uint8, order='C', copy=True)

    # Jaga-jaga terakhir
    img = np.ascontiguousarray(img)
    return img


def _downscale_if_needed(img: np.ndarray, max_w: int = MAX_DETECT_WIDTH) -> np.ndarray:
    """
    Perkecil gambar yang terlalu besar agar deteksi stabil & cepat.
    """
    h, w = img.shape[:2]
    if w > max_w:
        new_w = max_w
        new_h = int(h * (max_w / w))
        img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
    return img


def _load_image_rgb_uint8(path: str) -> np.ndarray:
    """
    Baca gambar apapun → kembalikan numpy RGB uint8 kontigu (H, W, 3).
    Try 1: face_recognition.load_image_file (RGB)
    Try 2: PIL + EXIF transpose + convert('RGB')
    Try 3: OpenCV + BGR→RGB
    """
    # Try 1 — face_recognition
    try:
        arr = face_recognition.load_image_file(path)  # RGB uint8
        if arr.dtype == np.uint8 and arr.ndim == 3:
            arr = arr[:, :, :3]  # jika 4 channel, potong ke 3
            return _coerce_rgb_uint8_c_writeable(arr)
    except Exception:
        pass

    # Try 2 — PIL
    try:
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im)
            if im.mode != "RGB":
                im = im.convert("RGB")
            arr = np.asarray(im, dtype=np.uint8)
            return _coerce_rgb_uint8_c_writeable(arr)
    except Exception:
        pass

    # Try 3 — OpenCV
    try:
        data = np.fromfile(path, dtype=np.uint8)     # aman untuk path Windows
        bgr = cv2.imdecode(data, cv2.IMREAD_COLOR)   # BGR uint8
        if bgr is None:
            raise ValueError("cv2.imdecode gagal")
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        return _coerce_rgb_uint8_c_writeable(rgb)
    except Exception:
        pass

    raise ValueError("Tidak bisa memuat sebagai RGB uint8 3-channel")


def _detect_locations_rgb(img_rgb_uint8: np.ndarray):
    """
    Deteksi lokasi wajah dari gambar RGB uint8 kontigu.
    Prioritas HOG, fallback CNN jika diaktifkan dan HOG error.
    """
    # Pastikan properti buffer
    img = _coerce_rgb_uint8_c_writeable(img_rgb_uint8)
    img = _downscale_if_needed(img, MAX_DETECT_WIDTH)

    # HOG dulu
    try:
        return face_recognition.face_locations(
            img,
            number_of_times_to_upsample=UPSAMPLE_HOG,
            model='hog'
        )
    except Exception as e:
        print("[WARN] HOG gagal:", e)
        if not USE_CNN_FALLBACK:
            raise

    # Fallback CNN
    try:
        return face_recognition.face_locations(
            img,
            number_of_times_to_upsample=0,
            model='cnn'
        )
    except Exception as e:
        print("[ERROR] CNN juga gagal:", e)
        raise


# ---------- API utama ----------
def load_known_faces(dataset_path='static/dataset'):
    global KNOWN_ENCODINGS, KNOWN_NAMES, FACES_LOADED

    if FACES_LOADED:
        print("[INFO] Wajah sudah dimuat. Skip.")
        return

    print("[INFO] Loading known faces...")
    if not os.path.exists(dataset_path):
        print(f"[ERROR] Folder dataset '{dataset_path}' tidak ditemukan!")
        return

    KNOWN_ENCODINGS, KNOWN_NAMES = [], []
    valid_exts = ('.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tif', '.tiff', '.heic', '.heif')

    for person_name in os.listdir(dataset_path):
        person_folder = os.path.join(dataset_path, person_name)
        if not os.path.isdir(person_folder):
            continue

        print(f"[INFO] Processing folder for: {person_name}")
        for file in os.listdir(person_folder):
            file_path = os.path.join(person_folder, file)
            if not file.lower().endswith(valid_exts):
                continue

            try:
                # Load → paksa RGB uint8 C-contig writeable → downscale jika perlu
                img = _load_image_rgb_uint8(file_path)
                img = _downscale_if_needed(img, MAX_DETECT_WIDTH)
                img = _coerce_rgb_uint8_c_writeable(img)

                # Lokasi wajah (HOG → CNN fallback)
                locs = _detect_locations_rgb(img)

                # Ambil encoding
                encs = face_recognition.face_encodings(img, locs)
                if encs:
                    # Simpan hanya satu encoding per file (pakai yang pertama)
                    KNOWN_ENCODINGS.append(encs[0])
                    KNOWN_NAMES.append(person_name)
                else:
                    print(f"[WARNING] Tidak ada wajah terdeteksi di {file_path}")

            except Exception as e:
                print(f"[ERROR] Gagal memproses gambar {file_path}: {e}")

    FACES_LOADED = True
    print(f"[INFO] Total wajah dikenal dimuat: {len(KNOWN_ENCODINGS)}")


def detect_face_from_image(image_bgr: np.ndarray):
    """
    Terima frame OpenCV (BGR), kembalikan nama jika match, else None.
    """
    # BGR → RGB
    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)

    # Paksa buffer benar + downscale
    rgb = _downscale_if_needed(_coerce_rgb_uint8_c_writeable(rgb), MAX_DETECT_WIDTH)

    # Lokasi + encoding
    locs = _detect_locations_rgb(rgb)
    encs = face_recognition.face_encodings(rgb, locs)

    for enc in encs:
        matches = face_recognition.compare_faces(
            KNOWN_ENCODINGS,
            enc,
            tolerance=1 - FACE_RECOGNITION_THRESHOLD
        )
        if True in matches:
            idx = matches.index(True)
            return KNOWN_NAMES[idx]
    return None
