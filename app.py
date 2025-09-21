from flask import Flask, render_template, request, redirect, url_for, session, flash, Response, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from requests_oauthlib import OAuth2Session
import requests
from recognizer import load_known_faces, detect_face_from_image
from datetime import datetime, timedelta
import os
import json
import cv2
import face_recognition
import base64
from PIL import Image
from io import BytesIO
import numpy as np
from googleapiclient.discovery import build
from oauth2client.service_account import ServiceAccountCredentials

# Import library untuk MySQL
from flask_mysqldb import MySQL
import MySQLdb.cursors
# Import decorator untuk role
from functools import wraps

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

app = Flask(__name__)
app.secret_key = 'supersecretkey'
app.permanent_session_lifetime = timedelta(hours=3)

# --- KONFIGURASI MYSQL ---
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = '' # Kosongkan jika XAMPP Anda tidak pakai password
app.config['MYSQL_DB'] = 'absensi_guru_db' # Pastikan nama database sama
app.config['MYSQL_CURSORCLASS'] = 'DictCursor' # Agar hasil query berupa dictionary

# Inisialisasi MySQL
mysql = MySQL(app)

# --- Konfigurasi Google Login & Path ---
GOOGLE_CLIENT_ID = '805710205906-9u3tvfrueflh7csfftibarqscr35erb5.apps.googleusercontent.com'
GOOGLE_CLIENT_SECRET = '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'
GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"
REDIRECT_URI = "http://localhost:5000/callback"
DATASET_PATH = 'static/dataset'

# --- Decorators untuk Autentikasi dan Otorisasi ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin' not in session and 'user' not in session:
            flash("Anda harus login untuk mengakses halaman ini.", "warning")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin' not in session:
            flash("Hanya admin yang dapat mengakses halaman ini.", "danger")
            # Jika user biasa mencoba akses, arahkan ke dasbor mereka
            if 'user' in session:
                return redirect(url_for('user_dashboard'))
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- Helper Functions ---
def get_google_provider_cfg():
    return requests.get(GOOGLE_DISCOVERY_URL, timeout=10).json()


# --- Routes ---

# --- Rute Autentikasi (Login, Register, Logout) ---
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        cursor = mysql.connection.cursor()
        
        # 1. Cek di tabel admin
        cursor.execute('SELECT * FROM admin WHERE username = %s', (username,))
        account = cursor.fetchone()

        if account and check_password_hash(account['password'], password):
            session['admin'] = account['username']
            session.permanent = True
            cursor.close()
            return redirect(url_for('dashboard')) # Admin ke dasbor utama

        # 2. Cek di tabel users
        cursor.execute('SELECT * FROM users WHERE username = %s', (username,))
        account = cursor.fetchone()
        
        if account and account.get('password') and check_password_hash(account['password'], password):
            session['user'] = account['username']
            session.permanent = True
            cursor.close()
            return redirect(url_for('user_dashboard')) # User ke dasbor user

        cursor.close()
        flash('❌ Username atau Password salah!', 'danger')
            
    return render_template("login.html")

@app.route('/register', methods=['GET', 'POST'])
def register():
    # Logika registrasi tetap sama
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        if not username or not email or not password or password != confirm_password:
            flash('❌ Data tidak valid atau password tidak cocok!', 'danger')
            return redirect(url_for('register'))

        cursor = mysql.connection.cursor()
        cursor.execute('SELECT * FROM users WHERE username = %s OR email = %s', (username, email))
        existing_user = cursor.fetchone()

        if existing_user:
            flash('⚠️ Username atau email sudah terdaftar!', 'warning')
            cursor.close()
            return redirect(url_for('register'))

        hashed_password = generate_password_hash(password)
        cursor.execute('INSERT INTO users (username, email, password) VALUES (%s, %s, %s)', (username, email, hashed_password))
        mysql.connection.commit()
        cursor.close()
        flash('✅ Registrasi berhasil! Silakan login.', 'success')
        return redirect(url_for('login'))
        
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('✅ Logout berhasil.', 'success')
    return redirect(url_for('login'))


# --- Rute Google Login ---
@app.route('/login/google')
def login_google():
    try:
        google_provider_cfg = get_google_provider_cfg()
        authorization_endpoint = google_provider_cfg["authorization_endpoint"]
        google = OAuth2Session(GOOGLE_CLIENT_ID, redirect_uri=REDIRECT_URI, scope=["openid", "email", "profile"])
        authorization_url, state = google.authorization_url(authorization_endpoint, access_type="offline", prompt="select_account")
        session['oauth_state'] = state
        return redirect(authorization_url)
    except requests.exceptions.RequestException as e:
        flash(f"Gagal terhubung ke layanan Google: {e}", "danger")
        return redirect(url_for("login"))


@app.route("/callback")
def callback():
    if 'oauth_state' not in session:
        flash("Sesi otentikasi tidak valid, silakan coba lagi.", "danger")
        return redirect(url_for("login"))
    try:
        google_provider_cfg = get_google_provider_cfg()
        token_endpoint = google_provider_cfg["token_endpoint"]

        google = OAuth2Session(GOOGLE_CLIENT_ID, state=session['oauth_state'], redirect_uri=REDIRECT_URI)
        token = google.fetch_token(token_endpoint, client_secret=GOOGLE_CLIENT_SECRET, authorization_response=request.url)
        
        user_info = google.get("https://openidconnect.googleapis.com/v1/userinfo").json()
        user_email = user_info.get('email')

        cursor = mysql.connection.cursor()
        cursor.execute('SELECT * FROM users WHERE email = %s', (user_email,))
        existing_user = cursor.fetchone()

        if not existing_user:
            username = user_info.get('name', user_email.split('@')[0])
            google_id = user_info.get('sub')
            cursor.execute('INSERT INTO users (username, email, google_id) VALUES (%s, %s, %s)', (username, user_email, google_id))
            mysql.connection.commit()
            flash(f"Akun Google Anda ({user_email}) berhasil didaftarkan!", "success")
        
        session['user'] = user_info.get('name')
        session.permanent = True
        cursor.close()
        return redirect(url_for("user_dashboard")) # Pengguna Google diarahkan ke dasbor user
    except Exception as e:
        flash(f"Terjadi kesalahan saat login dengan Google: {e}", "danger")
        return redirect(url_for("login"))


# --- Rute Utama Aplikasi ---

# RUTE KHUSUS ADMIN
@app.route('/dashboard')
@admin_required
def dashboard():
    cursor = mysql.connection.cursor()
    cursor.execute('SELECT COUNT(*) AS total FROM guru')
    jumlah_guru = cursor.fetchone()['total']
    
    today = datetime.now().strftime('%Y-%m-%d')
    cursor.execute('SELECT COUNT(*) AS total FROM absensi WHERE tanggal = %s AND waktu_masuk IS NOT NULL', (today,))
    jumlah_hadir = cursor.fetchone()['total']
    
    jumlah_belum_hadir = jumlah_guru - jumlah_hadir
    labels = []
    data_hadir = []
    data_belum_hadir = []
    
    for i in range(30):
        date_n_days_ago = datetime.now() - timedelta(days=29 - i)
        formatted_date = date_n_days_ago.strftime('%Y-%m-%d')
        labels.append(formatted_date)

        cursor.execute('SELECT COUNT(*) AS total FROM absensi WHERE tanggal = %s AND waktu_masuk IS NOT NULL', (formatted_date,))
        hadir_count = cursor.fetchone()['total']
        data_hadir.append(hadir_count)
        
        belum_hadir_count = jumlah_guru - hadir_count
        data_belum_hadir.append(belum_hadir_count)

    cursor.close()
    
    hari_libur = [{"tanggal": "2025-08-17", "keterangan": "Hari Kemerdekaan RI"}] 

    return render_template('dashboard.html',
        admin=session.get('admin'),
        jumlah_guru=jumlah_guru,
        jumlah_hadir=jumlah_hadir,
        jumlah_belum_hadir=jumlah_belum_hadir,
        labels=json.dumps(labels),
        data_hadir=json.dumps(data_hadir),
        data_belum_hadir=json.dumps(data_belum_hadir),
        hari_libur=json.dumps(hari_libur)
    )

# RUTE KHUSUS USER BIASA
@app.route('/user/dashboard')
@login_required
def user_dashboard():
    # Pastikan ini bukan admin yang nyasar
    if 'admin' in session:
        return redirect(url_for('dashboard'))
    return render_template('user_dashboard.html', user=session.get('user'))


# --- Rute Manajemen Guru (Hanya Admin) ---
@app.route('/register_face')
@admin_required
def register_face():
    return render_template('register_face.html')

@app.route('/save_faces', methods=['POST'])
@admin_required
def save_faces():
    try:
        name = request.form.get('nama')
        ttl = request.form.get('ttl', '')
        jenis_kelamin = request.form.get('jenis_kelamin', '')
        tahun_mulai_kerja = request.form.get('tahun_mulai_kerja', '')

        if not name:
            return jsonify({'success': False, 'message': 'Nama guru tidak boleh kosong.'}), 400

        guru_dataset_path = os.path.join(DATASET_PATH, name)
        os.makedirs(DATASET_PATH, exist_ok=True)
        
        cursor = mysql.connection.cursor()
        
        cursor.execute('SELECT id FROM guru WHERE nama = %s', (name,))
        existing_guru = cursor.fetchone()

        if existing_guru:
            cursor.execute('UPDATE guru SET ttl = %s, jenis_kelamin = %s, tahun_mulai_kerja = %s WHERE nama = %s',
                            (ttl, jenis_kelamin, tahun_mulai_kerja, name))
            message = f'Data guru "{name}" berhasil diperbarui.'
        else:
            cursor.execute('INSERT INTO guru (nama, ttl, jenis_kelamin, tahun_mulai_kerja) VALUES (%s, %s, %s, %s)',
                            (name, ttl, jenis_kelamin, tahun_mulai_kerja))
            message = f'Data guru "{name}" berhasil ditambahkan.'
        
        mysql.connection.commit()

        if os.path.exists(guru_dataset_path):
            import shutil
            shutil.rmtree(guru_dataset_path)
        os.makedirs(guru_dataset_path, exist_ok=True)

        for i in range(1, 6):
            file = request.files.get(f'image_{i}')
            if file:
                file.save(os.path.join(guru_dataset_path, f"{name}_pose_{i}.jpeg"))
            else:
                mysql.connection.rollback()
                cursor.close()
                return jsonify({'success': False, 'message': f'Pose ke-{i} tidak ditemukan.'}), 400

        load_known_faces()
        cursor.close()
        return jsonify({'success': True, 'message': message + ' Wajah berhasil disimpan.'})

    except MySQLdb.IntegrityError:
        mysql.connection.rollback()
        return jsonify({'success': False, 'message': 'Kesalahan: Nama guru sudah ada di database.'}), 500
    except Exception as e:
        mysql.connection.rollback()
        return jsonify({'success': False, 'message': f'Terjadi kesalahan internal: {str(e)}'}), 500

@app.route('/data_guru', methods=['GET', 'POST'])
@admin_required
def data_guru():
    if request.method == 'POST':
        try:
            nama_guru = request.form['nama']
            ttl = request.form['ttl']
            jenis_kelamin = request.form['jenis_kelamin']
            tahun_mulai_kerja = request.form['tahun_mulai_kerja']

            cursor = mysql.connection.cursor()
            cursor.execute('INSERT INTO guru (nama, ttl, jenis_kelamin, tahun_mulai_kerja) VALUES (%s, %s, %s, %s)',
                           (nama_guru, ttl, jenis_kelamin, tahun_mulai_kerja))
            mysql.connection.commit()
            cursor.close()
            flash('✅ Data guru berhasil ditambahkan.', 'success')
        except MySQLdb.IntegrityError:
            flash('⚠️ Nama guru sudah ada!', 'warning')
        except Exception as e:
            flash(f'❌ Terjadi kesalahan: {e}', 'danger')

    cursor = mysql.connection.cursor()
    cursor.execute('SELECT * FROM guru')
    gurus = cursor.fetchall()
    cursor.close()
    return render_template('data_guru.html', gurus=gurus)

@app.route('/edit_guru/<int:id>', methods=['GET', 'POST'])
@admin_required
def edit_guru(id):
    cursor = mysql.connection.cursor()
    
    if request.method == 'POST':
        nama = request.form['nama']
        ttl = request.form['ttl']
        jenis_kelamin = request.form['jenis_kelamin']
        tahun_mulai_kerja = request.form['tahun_mulai_kerja']
        cursor.execute('UPDATE guru SET nama = %s, ttl = %s, jenis_kelamin = %s, tahun_mulai_kerja = %s WHERE id = %s',
                       (nama, ttl, jenis_kelamin, tahun_mulai_kerja, id))
        mysql.connection.commit()
        cursor.close()
        flash('✅ Data guru berhasil diperbarui.', 'success')
        return redirect(url_for('data_guru'))

    cursor.execute('SELECT * FROM guru WHERE id = %s', (id,))
    guru = cursor.fetchone()
    cursor.close()
    if guru is None:
        flash('❌ Data guru tidak ditemukan.', 'danger')
        return redirect(url_for('data_guru'))
        
    return render_template('edit_guru.html', guru=guru)

@app.route('/hapus_guru/<int:id>')
@admin_required
def hapus_guru(id):
    try:
        cursor = mysql.connection.cursor()
        cursor.execute('DELETE FROM guru WHERE id = %s', (id,))
        mysql.connection.commit()
        cursor.close()
        flash('✅ Data guru berhasil dihapus.', 'success')
    except Exception as e:
        flash(f'❌ Gagal menghapus data: {e}', 'danger')
    return redirect(url_for('data_guru'))


# --- Rute yang Bisa Diakses Semua Role (Admin & User) ---
@app.route('/pindai_wajah', methods=['GET', 'POST'])
@login_required
def pindai_wajah():
    if request.method == 'POST':
        try:
            data_url = request.form.get('image')
            if not data_url or ',' not in data_url:
                return jsonify({'success': False, 'message': "Data gambar tidak valid."})

            _, encoded_data = data_url.split(',', 1)
            img_np = cv2.imdecode(np.frombuffer(base64.b64decode(encoded_data), np.uint8), cv2.IMREAD_COLOR)

            recognized_name = detect_face_from_image(img_np)

            if not recognized_name:
                return jsonify({'success': False, 'message': "❌ Wajah tidak dikenali."})

            today = datetime.now().strftime('%Y-%m-%d')
            waktu = datetime.now().strftime('%H:%M:%S')

            cursor = mysql.connection.cursor()
            cursor.execute('SELECT * FROM guru WHERE nama = %s', (recognized_name,))
            guru = cursor.fetchone()

            if not guru:
                cursor.close()
                return jsonify({'success': False, 'message': "Wajah dikenali, tapi tidak ada di database guru."})

            guru_id = guru['id']
            cursor.execute('SELECT * FROM absensi WHERE guru_id = %s AND tanggal = %s', (guru_id, today))
            absensi = cursor.fetchone()

            if absensi:
                if absensi['waktu_masuk'] and not absensi['waktu_keluar']:
                    cursor.execute('UPDATE absensi SET waktu_keluar = %s WHERE id = %s', (waktu, absensi['id']))
                    message = f"Sampai jumpa, {recognized_name}! Absen keluar berhasil."
                else:
                    cursor.close()
                    return jsonify({'success': False, 'message': f"Anda ({recognized_name}) sudah absen masuk dan keluar hari ini."})
            else:
                cursor.execute('INSERT INTO absensi (guru_id, waktu_masuk, tanggal) VALUES (%s, %s, %s)', (guru_id, waktu, today))
                message = f"Selamat datang, {recognized_name}! Absen masuk berhasil."

            mysql.connection.commit()
            cursor.close()
            return jsonify({'success': True, 'message': message})

        except Exception as e:
            print(f"ERROR in pindai_wajah: {e}")
            return jsonify({'success': False, 'message': f"Terjadi kesalahan server."})
    
    return render_template('pindai_absensi.html')


@app.route('/laporan')
@login_required
def laporan():
    cursor = mysql.connection.cursor()
    cursor.execute('''
        SELECT g.nama, a.waktu_masuk, a.waktu_keluar, a.tanggal
        FROM absensi a
        JOIN guru g ON a.guru_id = g.id
        ORDER BY a.tanggal DESC, a.waktu_masuk DESC
    ''')
    laporan_data = cursor.fetchall()
    cursor.close()
    return render_template('laporan.html', laporan=laporan_data)

if __name__ == '__main__':
    load_known_faces()
    app.run(debug=True)

