# recognizer.py — cepat & stabil (Windows-friendly)
# - Cache encodings ke disk (static/cache/encodings.pkl)
# - Loader kebal (PIL/face_recognition/OpenCV) → RGB uint8 C-contiguous writeable
# - Deteksi HOG (ringan) + opsi fallback CNN (dimatikan default)
# - Resize sebelum deteksi agar signifikan lebih cepat
# - Opsi parallel encode (off default, nyalakan bila dataset besar)

print("[DEBUG] recognizer loaded from:", __file__)

import os
import cv2
import time
import pickle
import hashlib
import numpy as np
import face_recognition
from typing import List, Tuple, Optional
from PIL import Image, ImageOps, ImageFile

ImageFile.LOAD_TRUNCATED_IMAGES = True

# Opsional: dukung HEIC/HEIF (foto iPhone)
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except Exception:
    pass

# ====== Konfigurasi kecepatan/deteksi ======
FACE_RECOGNITION_THRESHOLD = 0.55     # dipakai seperti sebelumnya: tolerance = 1 - THRESH
MAX_DETECT_WIDTH = 960                # 1600 → 960 = jauh lebih cepat di CPU
UPSAMPLE_HOG = 0                      # 0 cukup, 1 lebih teliti tapi lebih lambat
USE_CNN_FALLBACK = False              # matikan biar cepat; set True kalau perlu
VALID_EXTS = ('.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tif', '.tiff', '.heic', '.heif')

# ====== Cache ======
CACHE_DIR = "static/cache"
CACHE_PATH = os.path.join(CACHE_DIR, "encodings.pkl")

# ====== State global ======
KNOWN_ENCODINGS: List[np.ndarray] = []
KNOWN_NAMES: List[str] = []
FACES_LOADED = False


# ---------- Utilitas umum ----------
def _coerce_rgb_uint8_c_writeable(img: np.ndarray) -> np.ndarray:
    """Paksa array jadi RGB uint8 3-channel, C-contiguous & writeable."""
    if img.dtype != np.uint8:
        img = img.astype(np.uint8, copy=False)

    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
    elif img.ndim == 3 and img.shape[2] == 4:
        img = cv2.cvtColor(img, cv2.COLOR_RGBA2RGB)
    elif img.ndim == 3 and img.shape[2] != 3:
        raise ValueError(f"Channel tidak didukung: shape={img.shape}")

    img = np.require(img, dtype=np.uint8, requirements=['C', 'W'])
    if (not img.flags['C_CONTIGUOUS']) or (not img.flags['WRITEABLE']):
        img = np.array(img, dtype=np.uint8, order='C', copy=True)

    return np.ascontiguousarray(img)


def _downscale_if_needed(img: np.ndarray, max_w: int = MAX_DETECT_WIDTH) -> np.ndarray:
    """Perkecil gambar besar agar deteksi stabil & cepat."""
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
        data = np.fromfile(path, dtype=np.uint8)     # aman utk path Windows
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
    Prioritas HOG (ringan); fallback ke CNN jika diaktifkan.
    """
    img = _coerce_rgb_uint8_c_writeable(img_rgb_uint8)
    img = _downscale_if_needed(img, MAX_DETECT_WIDTH)

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

    # Fallback CNN (lambat; butuh dlib CNN detector internal)
    try:
        return face_recognition.face_locations(
            img,
            number_of_times_to_upsample=0,
            model='cnn'
        )
    except Exception as e:
        print("[ERROR] CNN juga gagal:", e)
        raise


# ---------- Cache helper ----------
def _dataset_signature(dataset_path: str) -> str:
    """Fingerprint dataset berdasar path file + mtime + size (stabil & cepat)."""
    h = hashlib.sha1()
    if not os.path.isdir(dataset_path):
        return ""
    for person in sorted(os.listdir(dataset_path)):
        pdir = os.path.join(dataset_path, person)
        if not os.path.isdir(pdir):
            continue
        for fn in sorted(os.listdir(pdir)):
            fp = os.path.join(pdir, fn)
            if not os.path.isfile(fp):
                continue
            st = os.stat(fp)
            h.update(person.encode("utf-8", errors="ignore"))
            h.update(fn.encode("utf-8", errors="ignore"))
            h.update(str(int(st.st_mtime)).encode("utf-8"))
            h.update(str(st.st_size).encode("utf-8"))
    return h.hexdigest()


def _try_load_cache(dataset_path: str):
    if not os.path.exists(CACHE_PATH):
        return None
    try:
        with open(CACHE_PATH, "rb") as f:
            data = pickle.load(f)
        if data.get("dataset_sig") == _dataset_signature(dataset_path):
            encs = data.get("encodings") or []
            names = data.get("names") or []
            print(f"[INFO] Loaded from cache: {len(encs)} encodings")
            return encs, names
    except Exception as e:
        print("[WARN] Cache gagal dibaca:", e)
    return None


def _save_cache(dataset_path: str, encs, names):
    os.makedirs(CACHE_DIR, exist_ok=True)
    data = {
        "dataset_sig": _dataset_signature(dataset_path),
        "encodings": encs,
        "names": names,
        "saved_at": time.time(),
    }
    with open(CACHE_PATH, "wb") as f:
        pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"[INFO] Cache disimpan: {CACHE_PATH} ({len(encs)} encodings)")


def invalidate_cache():
    """Opsional: panggil ini jika ingin paksa rebuild pada start berikutnya."""
    try:
        if os.path.exists(CACHE_PATH):
            os.remove(CACHE_PATH)
            print("[INFO] Cache dihapus.")
    except Exception as e:
        print("[WARN] Gagal hapus cache:", e)


# ---------- Encoder satu file (untuk parallel/serial) ----------
def _encode_one(file_path: str, person_name: str) -> Optional[Tuple[np.ndarray, str]]:
    try:
        img = _load_image_rgb_uint8(file_path)
        img = _downscale_if_needed(img, MAX_DETECT_WIDTH)
        img = _coerce_rgb_uint8_c_writeable(img)
        locs = _detect_locations_rgb(img)
        encs = face_recognition.face_encodings(img, locs)
        if encs:
            return (encs[0], person_name)
    except Exception as e:
        print(f"[ERROR] {file_path}: {e}")
    return None


# ---------- API utama ----------
def load_known_faces(
    dataset_path: str = 'static/dataset',
    use_cache: bool = True,
    force_rebuild: bool = False,
    use_parallel: bool = False,   # set True bila dataset besar dan bukan di debug-reloader
):
    """
    Muat seluruh face encodings dari dataset.
    - use_cache: ambil dari cache jika fingerprint dataset sama.
    - force_rebuild: abaikan cache & hitung ulang.
    - use_parallel: percepat dengan multiprocessing (hati2 di Windows + Flask debug).
    """
    global KNOWN_ENCODINGS, KNOWN_NAMES, FACES_LOADED

    if FACES_LOADED and not force_rebuild:
        print("[INFO] Wajah sudah dimuat. Skip.")
        return

    print("[INFO] Loading known faces...")
    if not os.path.exists(dataset_path):
        print(f"[ERROR] Folder dataset '{dataset_path}' tidak ditemukan!")
        return

    # ---- CACHE cepat ----
    if use_cache and not force_rebuild:
        cached = _try_load_cache(dataset_path)
        if cached:
            KNOWN_ENCODINGS, KNOWN_NAMES = cached
            FACES_LOADED = True
            print(f"[INFO] Total wajah dikenal dimuat: {len(KNOWN_ENCODINGS)}")
            return

    # ---- Build list pekerjaan ----
    jobs: List[Tuple[str, str]] = []
    for person_name in sorted(os.listdir(dataset_path)):
        person_folder = os.path.join(dataset_path, person_name)
        if not os.path.isdir(person_folder):
            continue
        print(f"[INFO] Processing folder for: {person_name}")
        for file in sorted(os.listdir(person_folder)):
            file_path = os.path.join(person_folder, file)
            if file.lower().endswith(VALID_EXTS) and os.path.isfile(file_path):
                jobs.append((file_path, person_name))

    KNOWN_ENCODINGS, KNOWN_NAMES = [], []

    # ---- Eksekusi (parallel atau serial) ----
    if use_parallel:
        try:
            from concurrent.futures import ProcessPoolExecutor, as_completed
            max_workers = max(1, (os.cpu_count() or 4) - 1)
            with ProcessPoolExecutor(max_workers=max_workers) as ex:
                futs = [ex.submit(_encode_one, fp, nm) for fp, nm in jobs]
                for fut in as_completed(futs):
                    res = fut.result()
                    if res:
                        enc, name = res
                        KNOWN_ENCODINGS.append(enc)
                        KNOWN_NAMES.append(name)
        except Exception as e:
            print("[WARN] Parallel gagal, fallback ke serial:", e)
            use_parallel = False  # lanjut serial

    if not use_parallel:
        for fp, nm in jobs:
            res = _encode_one(fp, nm)
            if res:
                enc, name = res
                KNOWN_ENCODINGS.append(enc)
                KNOWN_NAMES.append(name)

    # ---- Simpan cache ----
    if use_cache:
        _save_cache(dataset_path, KNOWN_ENCODINGS, KNOWN_NAMES)

    FACES_LOADED = True
    print(f"[INFO] Total wajah dikenal dimuat: {len(KNOWN_ENCODINGS)}")


def detect_face_from_image(image_bgr: np.ndarray) -> Optional[str]:
    """Terima frame OpenCV (BGR), kembalikan nama jika match, else None."""
    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    rgb = _downscale_if_needed(_coerce_rgb_uint8_c_writeable(rgb), MAX_DETECT_WIDTH)

    locs = _detect_locations_rgb(rgb)
    encs = face_recognition.face_encodings(rgb, locs)

    tol = 1 - FACE_RECOGNITION_THRESHOLD  # konsisten dgn versi kamu sebelumnya
    for enc in encs:
        matches = face_recognition.compare_faces(KNOWN_ENCODINGS, enc, tolerance=tol)
        if True in matches:
            idx = matches.index(True)
            return KNOWN_NAMES[idx]
    return None
