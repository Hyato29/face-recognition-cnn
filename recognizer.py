# recognizer.py
import face_recognition
import cv2
import os
import time
import numpy as np
from datetime import datetime

KNOWN_ENCODINGS = []
KNOWN_NAMES = []
FACES_LOADED = False
FACE_RECOGNITION_THRESHOLD = 0.55 

def load_known_faces(dataset_path='static/dataset'):
    global KNOWN_ENCODINGS, KNOWN_NAMES, FACES_LOADED

    if FACES_LOADED:
        print("[INFO] Wajah sudah diload sebelumnya. Skip reload.")
        return

    print("[INFO] Loading known faces...")
    if not os.path.exists(dataset_path):
        print(f"[ERROR] Folder dataset '{dataset_path}' tidak ditemukan!")
        return

    KNOWN_ENCODINGS = [] 
    KNOWN_NAMES = []

    for person_name in os.listdir(dataset_path):
        person_folder = os.path.join(dataset_path, person_name)
        if not os.path.isdir(person_folder):
            continue

        print(f"[INFO] Processing folder for: {person_name}")
        for file in os.listdir(person_folder):
            file_path = os.path.join(person_folder, file)
            if file.lower().endswith(('.png', '.jpg', '.jpeg')):
                try:
                    image = face_recognition.load_image_file(file_path)
                    face_encodings_in_image = face_recognition.face_encodings(image)

                    if face_encodings_in_image:
                        KNOWN_ENCODINGS.append(face_encodings_in_image[0])
                        KNOWN_NAMES.append(person_name)
                    else:
                        print(f"[WARNING] Tidak ada wajah terdeteksi di {file_path}")
                except Exception as e:
                    print(f"[ERROR] Gagal memproses gambar {file_path}: {e}")

    FACES_LOADED = True
    print(f"[INFO] Total wajah dikenal dimuat: {len(KNOWN_NAMES)}")

def detect_face_from_image(img_np):
    load_known_faces()
    if not KNOWN_ENCODINGS:
        print("[ERROR] Tidak ada wajah dikenal yang dimuat untuk perbandingan.")
        return None
    
    rgb_frame = cv2.cvtColor(img_np, cv2.COLOR_BGR2RGB)
    face_locations = face_recognition.face_locations(rgb_frame, model="cnn") 
    face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)

    recognized_name = None
    for face_encoding in face_encodings:
        matches = face_recognition.compare_faces(KNOWN_ENCODINGS, face_encoding, tolerance=FACE_RECOGNITION_THRESHOLD)
        face_distances = face_recognition.face_distance(KNOWN_ENCODINGS, face_encoding)

        best_match_index = -1
        min_distance = float('inf')

        for i, distance in enumerate(face_distances):
            if matches[i] and distance < min_distance:
                min_distance = distance
                best_match_index = i

        if best_match_index != -1:
            recognized_name = KNOWN_NAMES[best_match_index]
            print(f"[INFO] Wajah dikenali sebagai: {recognized_name} (Jarak: {min_distance:.2f})")
            break 

    if recognized_name is None:
        print("[INFO] Tidak ada wajah yang dikenali dalam gambar.")
    return recognized_name

def detect_face(timeout=10):
    print("[INFO] Memulai proses pindai wajah real-time...")

    if not KNOWN_ENCODINGS:
        print("[WARNING] Cache kosong. Melakukan reload dataset...")
        load_known_faces()

    if not KNOWN_ENCODINGS:
        print("[ERROR] Gagal memuat wajah dikenal. Deteksi dibatalkan.")
        return None

    cap = cv2.VideoCapture(0) 
    if not cap.isOpened():
        print("[ERROR] Kamera tidak dapat dibuka. Pastikan tidak ada aplikasi lain yang menggunakan kamera.")
        return None

    recognized_name = None
    start_time = time.time()

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("[ERROR] Gagal membaca frame kamera. Pastikan kamera berfungsi.")
                break

            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            face_locations = face_recognition.face_locations(rgb_frame)
            face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)

            for face_encoding in face_encodings:
                matches = face_recognition.compare_faces(KNOWN_ENCODINGS, face_encoding, tolerance=FACE_RECOGNITION_THRESHOLD)
                face_distances = face_recognition.face_distance(KNOWN_ENCODINGS, face_encoding)

                best_match_index = -1
                min_distance = float('inf')

                for i, distance in enumerate(face_distances):
                    if matches[i] and distance < min_distance:
                        min_distance = distance
                        best_match_index = i

                if best_match_index != -1:
                    recognized_name = KNOWN_NAMES[best_match_index]
                    print(f"[INFO] Wajah dikenali sebagai: {recognized_name} (Jarak: {min_distance:.2f})")
                    break 

            if recognized_name:
                break 
            if time.time() - start_time > timeout:
                print(f"[WARNING] Timeout ({timeout} detik): Wajah tidak dikenali.")
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()

    return recognized_name
