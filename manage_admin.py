import MySQLdb
from werkzeug.security import generate_password_hash
import getpass # Modul untuk input password secara aman (tidak terlihat saat diketik)

# --- SESUAIKAN DENGAN KONFIGURASI DATABASE ANDA ---
DB_HOST = "localhost"
DB_USER = "root"
DB_PASSWORD = ""
DB_NAME = "absensi_guru_db"
# --------------------------------------------------

def create_or_update_admin():
    """
    Fungsi interaktif untuk membuat admin baru atau mengubah password admin yang sudah ada.
    """
    try:
        # 1. Minta input dari pengguna
        target_username = input("Masukkan username untuk admin (contoh: admin): ")
        new_password = getpass.getpass(f"Masukkan password baru untuk '{target_username}': ")
        confirm_password = getpass.getpass(f"Konfirmasi password baru: ")

        # 2. Validasi input
        if not target_username or not new_password:
            print("\n❌ ERROR: Username dan password tidak boleh kosong.")
            return

        if new_password != confirm_password:
            print("\n❌ ERROR: Password dan konfirmasi tidak cocok.")
            return

        # 3. Buat koneksi ke database
        conn = MySQLdb.connect(host=DB_HOST, user=DB_USER, passwd=DB_PASSWORD, db=DB_NAME)
        cursor = conn.cursor()

        # 4. Hash password baru
        hashed_pw = generate_password_hash(new_password)

        # 5. Cek apakah username sudah ada di database
        cursor.execute("SELECT username FROM admin WHERE username = %s", (target_username,))
        user = cursor.fetchone()

        if user:
            # Jika user sudah ada, UPDATE password-nya
            cursor.execute('UPDATE admin SET password = %s WHERE username = %s', (hashed_pw, target_username))
            print(f"\n✅ BERHASIL: Password untuk admin '{target_username}' telah diperbarui.")
        else:
            # Jika user belum ada, INSERT data baru
            cursor.execute('INSERT INTO admin (username, password) VALUES (%s, %s)', (target_username, hashed_pw))
            print(f"\n✅ BERHASIL: Akun admin baru '{target_username}' telah dibuat.")
        
        # 6. Simpan perubahan ke database
        conn.commit()

    except MySQLdb.Error as e:
        print(f"\n❌ DATABASE ERROR: {e}")
        if 'conn' in locals() and conn.open:
            conn.rollback() # Batalkan perubahan jika terjadi error

    finally:
        # 7. Tutup koneksi
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals() and conn.open:
            conn.close()
            print("Koneksi ke database ditutup.")

if __name__ == '__main__':
    create_or_update_admin()
