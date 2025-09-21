from flask import Flask, render_template, request, redirect, url_for, session, flash, Response, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from requests_oauthlib import OAuth2Session
import requests
from recognizer import load_known_faces, detect_face
import sqlite3
from datetime import datetime, timedelta
import os
import json
import cv2
import face_recognition
import base64
from PIL import Image
from io import BytesIO
import numpy as np
from recognizer import detect_face_from_image
from db import get_db_connection
from googleapiclient.discovery import build
from oauth2client.service_account import ServiceAccountCredentials

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'  # ⚠️

app = Flask(__name__)
app.secret_key = 'supersecretkey'
app.permanent_session_lifetime = timedelta(hours=3)  

GOOGLE_CLIENT_ID = '805710205906-9u3tvfrueflh7csfftibarqscr35erb5.apps.googleusercontent.com'
GOOGLE_CLIENT_SECRET = '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'
GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"
REDIRECT_URI = "http://localhost:5000/callback"

DB_PATH = 'database/absensi.db'
DATASET_PATH = 'static/dataset'

def get_db_connection():
    if not hasattr(get_db_connection, 'initialized'):
        init_db()
        get_db_connection.initialized = True

    if not os.path.exists('database'):
        os.makedirs('database')
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS admin (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL
        )
    ''')
    if c.execute('SELECT COUNT(*) FROM admin').fetchone()[0] == 0:
        hashed_password = generate_password_hash('admin123')
        c.execute('INSERT INTO admin (username, password) VALUES (?, ?)', ('admin', hashed_password))
        print("✅ Admin default (admin/admin123) dibuat.")

    c.execute('''
        CREATE TABLE IF NOT EXISTS guru (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nama TEXT NOT NULL UNIQUE,
            ttl TEXT,
            jenis_kelamin TEXT,
            tahun_mulai_kerja INTEGER
        )
    ''')

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
    print("✅ Database berhasil diinisialisasi & tabel lengkap.")

def upgrade_table_guru():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("ALTER TABLE guru ADD COLUMN ttl TEXT")
        print("✅ Kolom 'ttl' berhasil ditambahkan.")
    except sqlite3.OperationalError:
        print("⚠️ Kolom 'ttl' sudah ada.")

    try:
        c.execute("ALTER TABLE guru ADD COLUMN jenis_kelamin TEXT")
        print("✅ Kolom 'jenis_kelamin' berhasil ditambahkan.")
    except sqlite3.OperationalError:
        print("⚠️ Kolom 'jenis_kelamin' sudah ada.")

    try:
        c.execute("ALTER TABLE guru ADD COLUMN tahun_mulai_kerja INTEGER")
        print("✅ Kolom 'tahun_mulai_kerja' berhasil ditambahkan.")
    except sqlite3.OperationalError:
        print("⚠️ Kolom 'tahun_mulai_kerja' sudah ada.")

    conn.commit()
    conn.close()

upgrade_table_guru()

def get_google_provider_cfg():
    # Tambahkan timeout untuk mencegah hang
    return requests.get(GOOGLE_DISCOVERY_URL, timeout=10).json()

def deteksi_wajah():
    nama_terdeteksi = "Ahmad"
    conn = get_db_connection()
    guru = conn.execute("SELECT id FROM guru WHERE nama = ?", (nama_terdeteksi,)).fetchone()
    conn.close()
    return guru['id'] if guru else None

def login_required():
    return 'admin' in session or 'user' in session

def get_hari_libur():
    SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
    credentials = ServiceAccountCredentials.from_json_keyfile_name('YOUR-CREDENTIAL.json', scopes=SCOPES)
    service = build('calendar', 'v3', credentials=credentials)
    
    now = datetime.datetime.utcnow().isoformat() + 'Z'
    events = service.events().list(
        calendarId='id.indonesian#holiday@group.v.calendar.google.com',
        timeMin=now,
        maxResults=20,
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    
    holidays = []
    for event in events.get('items', []):
        holidays.append(event['start']['date'])
    return holidays

def detect_face_from_image(image):
    import face_recognition
    from recognizer import KNOWN_ENCODINGS, KNOWN_NAMES, FACE_RECOGNITION_THRESHOLD

    rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    face_locations = face_recognition.face_locations(rgb_image)
    face_encodings = face_recognition.face_encodings(rgb_image, face_locations)

    for face_encoding in face_encodings:
        matches = face_recognition.compare_faces(KNOWN_ENCODINGS, face_encoding, tolerance=1 - FACE_RECOGNITION_THRESHOLD)
        if True in matches:
            matched_idx = matches.index(True)
            return KNOWN_NAMES[matched_idx]

    return None


@app.route('/login/google')
def login_google():
    google_provider_cfg = get_google_provider_cfg()
    authorization_endpoint = google_provider_cfg["authorization_endpoint"]

    google = OAuth2Session(GOOGLE_CLIENT_ID, redirect_uri=REDIRECT_URI, scope=["openid", "email", "profile"])
  
    authorization_url, state = google.authorization_url(authorization_endpoint, access_type="offline", prompt="select_account")

    session['oauth_state'] = state
    return redirect(authorization_url)

@app.route("/callback")
def callback():
    # Pastikan 'oauth_state' ada di session
    if 'oauth_state' not in session:
        flash("❌ Sesi OAuth tidak valid atau kedaluwarsa. Silakan coba login lagi.", "danger")
        print("❌ ERROR: 'oauth_state' tidak ditemukan di session.")
        return redirect(url_for("login"))

    try:
        # Ambil konfigurasi dari Google
        google_provider_cfg = get_google_provider_cfg()
        token_endpoint = google_provider_cfg["token_endpoint"]

        # Inisialisasi OAuth2Session
        google = OAuth2Session(GOOGLE_CLIENT_ID, state=session['oauth_state'], redirect_uri=REDIRECT_URI)

        # Ambil token
        # Gunakan try-except untuk fetch_token
        try:
            token = google.fetch_token(
                token_endpoint,
                client_secret=GOOGLE_CLIENT_SECRET,
                authorization_response=request.url
            )
            print("✅ Token berhasil diambil:", token)
        except Exception as e:
            flash(f"❌ Gagal mengambil token dari Google: {e}", "danger")
            print(f"❌ ERROR: Gagal mengambil token: {e}")
            return redirect(url_for("login"))

        # Ambil informasi user dari Google
        # Gunakan try-except untuk permintaan userinfo
        try:
            resp = google.get("https://openidconnect.googleapis.com/v1/userinfo", timeout=5)
            resp.raise_for_status()  # Akan memunculkan HTTPError untuk status kode 4xx/5xx
            user_info = resp.json()
            print("✅ Data user:", user_info)
        except requests.exceptions.RequestException as e:
            flash(f"❌ Gagal mengambil informasi pengguna dari Google: {e}", "danger")
            print(f"❌ ERROR: Gagal mengambil userinfo: {e}")
            return redirect(url_for("login"))
        except json.JSONDecodeError:
            flash("❌ Respon dari Google bukan JSON yang valid.", "danger")
            print("❌ ERROR: Respon userinfo bukan JSON.")
            return redirect(url_for("login"))

        # Simpan informasi user ke session
        session['profile'] = {
            'name': user_info.get('name'),
            'email': user_info.get('email'),
            'picture': user_info.get('picture')
        }
        
        # Hapus state dari session setelah digunakan
        session.pop('oauth_state', None)

        # Cek apakah user sudah terdaftar di database
        conn = get_db_connection()
        user_email = user_info.get('email')
        existing_user = conn.execute('SELECT * FROM users WHERE email = ?', (user_email,)).fetchone()

        if not existing_user:
            # Jika belum terdaftar, daftarkan user baru
            username = user_info.get('name', user_email.split('@')[0]) # Ambil nama atau bagian email sebelum @
            google_id = user_info.get('sub') # 'sub' adalah ID unik Google
            try:
                conn.execute('INSERT INTO users (username, email, google_id) VALUES (?, ?, ?)',
                             (username, user_email, google_id))
                conn.commit()
                flash(f"✅ Akun Google Anda ({user_email}) berhasil didaftarkan dan login!", "success")
                print(f"✅ User baru didaftarkan: {username} ({user_email})")
            except sqlite3.IntegrityError:
                # Ini bisa terjadi jika ada race condition atau user mencoba daftar lagi
                flash("⚠️ Akun Google Anda sudah terdaftar. Silakan login.", "warning")
                print(f"⚠️ User {user_email} sudah ada, mungkin karena race condition.")
            except Exception as e:
                flash(f"❌ Gagal menyimpan data user Google: {e}", "danger")
                print(f"❌ ERROR: Gagal menyimpan user Google: {e}")
                conn.close()
                return redirect(url_for("login"))
        else:
            flash(f"✅ Selamat datang kembali, {user_info.get('name')}! Anda berhasil login dengan Google.", "success")
            print(f"✅ User {user_email} berhasil login.")

        # Set session 'user' untuk menandakan login berhasil
        session['user'] = user_info.get('email') # Atau bisa juga user_info.get('name')

        conn.close()
        return redirect(url_for("dashboard"))

    except requests.exceptions.Timeout:
        flash("❌ Permintaan ke Google API mengalami timeout. Coba lagi.", "danger")
        print("❌ ERROR: Google API request timed out.")
        return redirect(url_for("login"))
    except requests.exceptions.ConnectionError:
        flash("❌ Gagal terhubung ke Google API. Periksa koneksi internet Anda.", "danger")
        print("❌ ERROR: Gagal terhubung ke Google API.")
        return redirect(url_for("login"))
    except Exception as e:
        flash(f"❌ Terjadi kesalahan tak terduga saat login dengan Google: {e}", "danger")
        print(f"❌ ERROR tak terduga di callback: {e}")
        return redirect(url_for("login"))

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db_connection()
        admin = conn.execute('SELECT * FROM admin WHERE username = ?', (username,)).fetchone()
        conn.close()
        if admin and check_password_hash(admin['password'], password):
            session['admin'] = admin['username']
            return redirect(url_for('dashboard'))
        else:
            flash('❌ Username atau Password salah!', 'danger')

    # Perbaikan: flash message untuk login Google yang berhasil
    # Ini akan dipicu jika redirect dari callback berhasil
    if 'login_success' in session:
        flash(session.pop('login_success'), 'success')

    return render_template("login.html")

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        if not username or not email or not password:
            flash('❌ Semua field wajib diisi!', 'danger')
            return redirect(url_for('register'))
        if password != confirm_password:
            flash('❌ Password dan konfirmasi tidak sama!', 'danger')
            return redirect(url_for('register'))

        conn = get_db_connection()
        existing_user = conn.execute('SELECT * FROM users WHERE username = ? OR email = ?', (username, email)).fetchone()
        if existing_user:
            flash('⚠️ Username atau email sudah terdaftar!', 'warning')
            conn.close()
            return redirect(url_for('register'))

        hashed_password = generate_password_hash(password)
        conn.execute('INSERT INTO users (username, email, password) VALUES (?, ?, ?)',
                     (username, email, hashed_password))
        conn.commit()
        conn.close()
        flash('✅ Registrasi berhasil! Silakan login.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('✅ Logout berhasil.', 'success')
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if not login_required():  
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    jumlah_guru = conn.execute('SELECT COUNT(*) FROM guru').fetchone()[0]
    today = datetime.now().strftime('%Y-%m-%d')
    jumlah_hadir = conn.execute(
        'SELECT COUNT(*) FROM absensi WHERE tanggal = ? AND waktu_masuk IS NOT NULL',
        (today,)
    ).fetchone()[0]
    jumlah_belum_hadir = jumlah_guru - jumlah_hadir
    labels = []
    data_hadir = []
    data_belum_hadir = []
    hari_libur = [{"tanggal": "2025-08-17", "keterangan": "Hari Kemerdekaan"}]

    for i in range(30):
        date_n_days_ago = datetime.now() - timedelta(days=29 - i)
        formatted_date = date_n_days_ago.strftime('%Y-%m-%d')
        labels.append(formatted_date)

        hadir_count = conn.execute(
            'SELECT COUNT(*) FROM absensi WHERE tanggal = ? AND waktu_masuk IS NOT NULL',
            (formatted_date,)
        ).fetchone()[0]
        data_hadir.append(hadir_count)
        belum_hadir_count = jumlah_guru - hadir_count
        data_belum_hadir.append(belum_hadir_count)
        hari_libur = [
        {"tanggal": "2025-01-01", "keterangan": "Tahun Baru Masehi"},
        {"tanggal": "2025-08-17", "keterangan": "Hari Kemerdekaan RI"},
        {"tanggal": "2025-12-25", "keterangan": "Hari Raya Natal"}
        ]
    conn.close()

    return render_template('dashboard.html',
        admin=session.get('admin') or session.get('user'),
        jumlah_guru=jumlah_guru,
        jumlah_hadir=jumlah_hadir,
        jumlah_belum_hadir=jumlah_belum_hadir,
        labels=json.dumps(labels),
        data_hadir=json.dumps(data_hadir),
        data_belum_hadir=json.dumps(data_belum_hadir),
        hari_libur=json.dumps(hari_libur)
    )

@app.route('/register_face')
def register_face():
    return render_template('register_face.html')

@app.route('/save_faces', methods=['POST'])
def save_faces():
    try:
        # Ambil data dari form
        name = request.form.get('nama')
        ttl = request.form.get('ttl', '')
        jenis_kelamin = request.form.get('jenis_kelamin', '')
        tahun_mulai_kerja = request.form.get('tahun_mulai_kerja', '')

        if not name:
            return jsonify({'success': False, 'message': 'Nama guru tidak boleh kosong.'}), 400

        # Definisikan path utama dataset
        DATASET_PATH = os.path.join('static', 'dataset')
        guru_dataset_path = os.path.join(DATASET_PATH, name)

        # Pastikan folder dataset utama ada
        if not os.path.exists(DATASET_PATH):
            os.makedirs(DATASET_PATH)

        # Koneksi ke database
        conn = get_db_connection()
        try:
            existing_guru = conn.execute('SELECT id FROM guru WHERE nama = ?', (name,)).fetchone()

            if existing_guru:
                # Cek apakah guru sudah punya dataset wajah lengkap
                if os.path.exists(guru_dataset_path) and os.path.isdir(guru_dataset_path) and len(os.listdir(guru_dataset_path)) >= 5:
                    return jsonify({'success': False, 'message': f'Guru dengan nama "{name}" sudah terdaftar dan memiliki dataset wajah. Tidak bisa mendaftar ulang.'}), 409
                else:
                    # Update data guru
                    conn.execute('''
                        UPDATE guru
                        SET ttl = ?, jenis_kelamin = ?, tahun_mulai_kerja = ?
                        WHERE nama = ?
                    ''', (ttl, jenis_kelamin, tahun_mulai_kerja, name))
                    conn.commit()
                    message = f'Data guru "{name}" berhasil diperbarui. Wajah akan disimpan ulang.'
            else:
                # Insert data guru baru
                conn.execute('''
                    INSERT INTO guru (nama, ttl, jenis_kelamin, tahun_mulai_kerja)
                    VALUES (?, ?, ?, ?)
                ''', (name, ttl, jenis_kelamin, tahun_mulai_kerja))
                conn.commit()
                message = f'Data guru "{name}" berhasil ditambahkan.'

            # Hapus folder lama jika ada
            if os.path.exists(guru_dataset_path):
                import shutil
                shutil.rmtree(guru_dataset_path)

            # Buat folder baru
            os.makedirs(guru_dataset_path, exist_ok=True)

            # Simpan 5 gambar pose wajah
            for i in range(1, 6):
                file = request.files.get(f'image_{i}')
                if file:
                    filename = f"{name}_pose_{i}.jpeg"
                    file.save(os.path.join(guru_dataset_path, filename))
                else:
                    # Jika pose tidak lengkap, hapus folder
                    shutil.rmtree(guru_dataset_path)
                    return jsonify({'success': False, 'message': f'Pose ke-{i} tidak ditemukan. Pastikan 5 pose diambil.'}), 400

            # Reload wajah yang dikenal
            from recognizer import FACES_LOADED, load_known_faces
            FACES_LOADED = False
            load_known_faces()

            return jsonify({'success': True, 'message': message + ' Wajah berhasil disimpan ke dataset.'})

        except sqlite3.IntegrityError as e:
            return jsonify({'success': False, 'message': f'Kesalahan database: {str(e)}. Mungkin nama guru sudah ada.'}), 500
        except Exception as e:
            return jsonify({'success': False, 'message': f'Terjadi kesalahan saat menyimpan data: {str(e)}'}), 500
        finally:
            conn.close()
    except Exception as e:
        return jsonify({'success': False, 'message': f'Terjadi kesalahan pada request: {str(e)}'}), 500

@app.route('/data_guru', methods=['GET', 'POST'])
def data_guru():
    if 'admin' not in session and 'user' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()

    if request.method == 'POST':
        try:
            nama_guru = request.form['nama']
            ttl = request.form['ttl']
            jenis_kelamin = request.form['jenis_kelamin']
            tahun_mulai_kerja = request.form['tahun_mulai_kerja']

            conn.execute('''
                INSERT INTO guru (nama, ttl, jenis_kelamin, tahun_mulai_kerja)
                VALUES (?, ?, ?, ?)
            ''', (nama_guru, ttl, jenis_kelamin, tahun_mulai_kerja))
            conn.commit()
            flash('✅ Data guru berhasil ditambahkan.', 'success')
        except sqlite3.IntegrityError:
            flash('⚠️ Nama guru sudah ada!', 'warning')
        except Exception as e:
            flash(f'❌ Terjadi kesalahan: {e}', 'danger')

    gurus = conn.execute('SELECT * FROM guru').fetchall()
    conn.close()
    return render_template('data_guru.html', gurus=gurus)

@app.route('/edit_guru/<int:id>', methods=['GET', 'POST'])
def edit_guru(id):
    if 'admin' not in session and 'user' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    guru = conn.execute('SELECT * FROM guru WHERE id = ?', (id,)).fetchone()

    if guru is None:
        flash('❌ Data guru tidak ditemukan.', 'danger')
        return redirect(url_for('data_guru'))

    if request.method == 'POST':
        nama = request.form['nama']
        ttl = request.form['ttl']
        jenis_kelamin = request.form['jenis_kelamin']
        tahun_mulai_kerja = request.form['tahun_mulai_kerja']

        conn.execute('''
            UPDATE guru
            SET nama = ?, ttl = ?, jenis_kelamin = ?, tahun_mulai_kerja = ?
            WHERE id = ?
        ''', (nama, ttl, jenis_kelamin, tahun_mulai_kerja, id))
        conn.commit()
        conn.close()
        flash('✅ Data guru berhasil diperbarui.', 'success')
        return redirect(url_for('data_guru'))

    conn.close()
    return render_template('edit_guru.html', guru=guru)

@app.route('/hapus_guru/<int:id>')
def hapus_guru(id):
    if 'admin' not in session and 'user' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    conn.execute('DELETE FROM guru WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    flash('✅ Data guru berhasil dihapus.', 'success')
    return redirect(url_for('data_guru'))

@app.route('/pindai_wajah')
def pindai_wajah():
    if 'admin' not in session and 'user' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('pindai_absensi'))

@app.route('/pindai_absensi', methods=['GET', 'POST'])
def pindai_absensi():
    if 'admin' not in session and 'user' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        try:
            data_url = request.form.get('image')
            if not data_url or ',' not in data_url:
                return jsonify({'success': False, 'message': "Data gambar tidak valid."})

            _, encoded_data = data_url.split(',', 1)
            decoded_data = base64.b64decode(encoded_data)
            np_arr = np.frombuffer(decoded_data, np.uint8)
            img_np = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

            recognized_name = detect_face_from_image(img_np)

            if not recognized_name:
                return jsonify({'success': False, 'message': "❌ Wajah tidak dikenali. Pastikan wajah terlihat jelas di kamera."})

            today = datetime.now().strftime('%Y-%m-%d')
            waktu = datetime.now().strftime('%H:%M:%S')

            conn = get_db_connection()
            guru = conn.execute('SELECT * FROM guru WHERE nama = ?', (recognized_name,)).fetchone()

            if not guru:
                return jsonify({'success': False, 'message': "✅ Wajah dikenali, tapi tidak ditemukan dalam database guru."})

            guru_id = guru['id']
            absensi = conn.execute('SELECT * FROM absensi WHERE guru_id = ? AND tanggal = ?', (guru_id, today)).fetchone()

            if absensi:
                if not absensi['waktu_masuk']:
                    conn.execute('UPDATE absensi SET waktu_masuk = ? WHERE id = ?', (waktu, absensi['id']))
                    conn.commit()
                    return jsonify({'success': True, 'message': f"Selamat datang, {recognized_name}! Absensi masuk berhasil pada {waktu}."})
                elif not absensi['waktu_keluar']:
                    conn.execute('UPDATE absensi SET waktu_keluar = ? WHERE id = ?', (waktu, absensi['id']))
                    conn.commit()
                    return jsonify({'success': True, 'message': f"Sampai jumpa, {recognized_name}! Absensi keluar berhasil pada {waktu}."})
                else:
                    return jsonify({'success': False, 'message': f"Anda ({recognized_name}) sudah absen masuk dan keluar hari ini."})
            else:
                conn.execute('INSERT INTO absensi (guru_id, waktu_masuk, tanggal) VALUES (?, ?, ?)', (guru_id, waktu, today))
                conn.commit()
                return jsonify({'success': True, 'message': f"Selamat datang, {recognized_name}! Absensi masuk berhasil pada {waktu}."})

        except Exception as e:
            return jsonify({'success': False, 'message': f"Terjadi kesalahan: {str(e)}"})

        finally:
            if 'conn' in locals():
                conn.close()

    return render_template('pindai_absensi.html')

@app.route('/laporan')
def laporan():
    if 'admin' not in session and 'user' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    laporan_data = conn.execute('''
        SELECT g.nama, a.waktu_masuk, a.waktu_keluar, a.tanggal
        FROM absensi a
        JOIN guru g ON a.guru_id = g.id
        ORDER BY a.tanggal DESC, a.waktu_masuk DESC
    ''').fetchall()
    conn.close()
    return render_template('laporan.html', laporan=laporan_data)

with open('static/dataset/test123/test.jpg', 'w') as f:
    f.write('uji simpan dari flask')
    
if __name__ == '__main__':
    init_db()
    app.run(debug=True)

