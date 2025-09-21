import sqlite3
from werkzeug.security import generate_password_hash

conn = sqlite3.connect('database/absensi.db')
c = conn.cursor()

hashed_pw = generate_password_hash('admin123')
c.execute('UPDATE admin SET password = ? WHERE username = ?', (hashed_pw, 'admin'))
conn.commit()
conn.close()

print("✅ Password admin sudah dihash ulang.")
