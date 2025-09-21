import sqlite3
import os
from werkzeug.security import generate_password_hash

# === PATH DATABASE ===
db_folder = 'database'
db_path = os.path.join(db_folder, 'absensi.db')

# 📁 Buat folder database jika belum ada
if not os.path.exists(db_folder):
    os.makedirs(db_folder)

# 📦 Fungsi inisialisasi database
def init_db():
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # === Tabel ADMIN ===
    c.execute('''
    CREATE TABLE IF NOT EXISTS admin (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password TEXT NOT NULL
    )
    ''')
    # Tambahkan admin default jika belum ada
    hashed_password = generate_password_hash('admin123')
    c.execute('SELECT COUNT(*) FROM admin')
    if c.fetchone()[0] == 0:
        c.execute('INSERT INTO admin (username, password) VALUES (?, ?)',
                  ('admin', hashed_password))
        print("✅ Admin default dibuat (username: admin, password: admin123).")

    # === Tabel GURU ===
    c.execute('''
    CREATE TABLE IF NOT EXISTS guru (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nama TEXT NOT NULL UNIQUE,
        ttl TEXT,
        jenis_kelamin TEXT,
        tahun_mulai_kerja INTEGER
    )
    ''')

    # === Tabel ABSENSI ===
    c.execute('''
    CREATE TABLE IF NOT EXISTS absensi (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guru_id INTEGER NOT NULL,
        waktu_masuk TEXT,
        waktu_keluar TEXT,
        tanggal TEXT NOT NULL,
        FOREIGN KEY (guru_id) REFERENCES guru(id)
    )
    ''')

    # === Tabel USERS ===
    c.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        email TEXT NOT NULL UNIQUE,
        password TEXT,
        google_id TEXT UNIQUE
    )
    ''')

    conn.commit()
    conn.close()
    print("🎉 Database & semua tabel berhasil dibuat.")

# 🏃 Jalankan inisialisasi saat file diimport
init_db()
