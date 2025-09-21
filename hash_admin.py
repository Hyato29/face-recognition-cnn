# file: hash_admin.py (versi baru untuk MySQL)
import MySQLdb
from werkzeug.security import generate_password_hash
import getpass # Untuk input password yang aman

# --- SESUAIKAN DENGAN KONFIGURASI DATABASE ANDA ---
DB_HOST = "localhost"
DB_USER = "root"
DB_PASSWORD = ""
DB_NAME = "absensi_guru_db"
# --------------------------------------------------

def update_or_create_admin():
    target_username = input("Masukkan username admin (cth: admin): ")
    new_password = getpass.getpass(f"Masukkan password baru untuk '{target_username}': ")

    if not target_username or not new_password:
        print("❌ Username dan password tidak boleh kosong.")
        return

    try:
        conn = MySQLdb.connect(host=DB_HOST, user=DB_USER, passwd=DB_PASSWORD, db=DB_NAME)
        c = conn.cursor()

        hashed_pw = generate_password_hash(new_password)

        # Cek apakah username sudah ada
        c.execute("SELECT * FROM admin WHERE username = %s", (target_username,))
        user = c.fetchone()

        if user:
            # Jika ada, update passwordnya
            c.execute('UPDATE admin SET password = %s WHERE username = %s', (hashed_pw, target_username))
            print(f"✅ Password untuk username '{target_username}' berhasil diupdate.")
        else:
            # Jika tidak ada, buat admin baru
            c.execute('INSERT INTO admin (username, password) VALUES (%s, %s)', (target_username, hashed_pw))
            print(f"✅ Admin baru dengan username '{target_username}' berhasil dibuat.")
        
        conn.commit()

    except MySQLdb.Error as e:
        print(f"❌ Terjadi error pada database: {e}")

    finally:
        if 'conn' in locals() and conn.open:
            conn.close()

if __name__ == '__main__':
    update_or_create_admin()