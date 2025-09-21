import MySQLdb
from datetime import datetime

# --- SESUAIKAN DENGAN KONFIGURASI DATABASE ANDA ---
DB_HOST = "localhost"
DB_USER = "root"
DB_PASSWORD = ""
DB_NAME = "absensi_guru_db"
# --------------------------------------------------

# --- DATA GURU DARI GAMBAR ANDA ---
data_guru = [
    {"nama": "MUHRIM,S.Pd", "ttl": "Perigi, 12-04-1970", "jenis_kelamin": "Laki-Laki", "tahun_mulai_kerja": 2005},
    {"nama": "JUMATI,S.Pd", "ttl": "Perigi, 12-03-1971", "jenis_kelamin": "Perempuan", "tahun_mulai_kerja": 2005},
    {"nama": "NURSIDIN,S.Pdi", "ttl": "Perigi, 10-05-1981", "jenis_kelamin": "Laki-Laki", "tahun_mulai_kerja": 2007},
    {"nama": "SAHNUR,S.Pd", "ttl": "Perigi, 12-06-1983", "jenis_kelamin": "Perempuan", "tahun_mulai_kerja": 2007},
    {"nama": "RENA AGUSTIA,S.Pd", "ttl": "Perigi, 10-08-1989", "jenis_kelamin": "Perempuan", "tahun_mulai_kerja": 2009},
    {"nama": "DIA UNNUR,S.Pd", "ttl": "Perigi, 12-12-1988", "jenis_kelamin": "Perempuan", "tahun_mulai_kerja": 2009}
]
# ------------------------------------

def seed_data():
    conn = None  # Inisialisasi koneksi
    try:
        # Buat koneksi ke database
        conn = MySQLdb.connect(host=DB_HOST, user=DB_USER, passwd=DB_PASSWORD, db=DB_NAME)
        c = conn.cursor()

        print("Menambahkan data guru ke database...")
        
        added_count = 0
        for guru in data_guru:
            # Gunakan INSERT IGNORE untuk menghindari error jika data sudah ada (berdasarkan NAMA yang UNIQUE)
            query = """
                INSERT IGNORE INTO guru (nama, ttl, jenis_kelamin, tahun_mulai_kerja) 
                VALUES (%s, %s, %s, %s)
            """
            values = (guru["nama"], guru["ttl"], guru["jenis_kelamin"], guru["tahun_mulai_kerja"])
            
            # Eksekusi query
            c.execute(query, values)
            if c.rowcount > 0: # rowcount akan > 0 jika ada baris baru yang ditambahkan
                print(f"  -> Berhasil menambahkan: {guru['nama']}")
                added_count += 1
            else:
                print(f"  -> Data sudah ada (skip): {guru['nama']}")

        # Commit (simpan) semua perubahan ke database
        conn.commit()
        
        print("\n-------------------------------------------")
        print(f"✅ Selesai! {added_count} data guru baru berhasil ditambahkan.")
        print("-------------------------------------------")

    except MySQLdb.Error as e:
        print(f"❌ Terjadi error pada database: {e}")
        if conn:
            conn.rollback() # Batalkan semua perubahan jika terjadi error

    finally:
        # Pastikan koneksi selalu ditutup
        if conn and conn.open:
            conn.close()

# Jalankan fungsi saat skrip dieksekusi
if __name__ == '__main__':
    seed_data()
