const video = document.getElementById("video");
const captureBtn = document.getElementById("captureBtn");
const saveBtn = document.getElementById("saveBtn");
const stopCameraBtn = document.getElementById("stopCameraBtn");
const namaInput = document.getElementById("nama");
const statusDiv = document.getElementById("status");

// Preview container
const previewContainer = document.getElementById("previewContainer");
let stream;
let capturedImages = [];

// Menyalakan kamera
async function startCamera() {
    try {
        stream = await navigator.mediaDevices.getUserMedia({ video: true });
        video.srcObject = stream;
    } catch (err) {
        statusDiv.textContent = "🚫 Tidak dapat mengakses kamera.";
        statusDiv.style.color = "red";
    }
}

// Mematikan kamera
function stopCamera() {
    if (stream) {
        stream.getTracks().forEach(track => track.stop());
        video.srcObject = null;
        statusDiv.textContent = "📴 Kamera dimatikan.";
        statusDiv.style.color = "black";
    }
}

// Menangkap satu gambar pose
function captureImage() {
    if (!namaInput.value.trim()) {
        alert("Masukkan nama guru terlebih dahulu.");
        return;
    }

    if (capturedImages.length >= 5) {
        alert("Sudah cukup 5 pose. Klik 'Simpan Wajah'.");
        return;
    }

    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d").drawImage(video, 0, 0);
    canvas.toBlob(blob => {
        capturedImages.push(blob);

        const img = document.createElement("img");
        img.src = URL.createObjectURL(blob);
        img.width = 100;
        img.style.margin = "5px";
        previewContainer.appendChild(img);

        statusDiv.textContent = `📸 Pose ${capturedImages.length} ditambahkan.`;
        statusDiv.style.color = "green";
    }, "image/jpeg");
}

// Mengirim 5 gambar ke server
async function submitImages() {
    const nama = namaInput.value.trim();
    const ttl = document.getElementById("ttl").value.trim();
    const jenisKelamin = document.getElementById("jenis_kelamin").value;
    const tahunMulaiKerja = document.getElementById("tahun_mulai_kerja").value.trim();

    if (!nama || !ttl || !jenisKelamin || !tahunMulaiKerja) {
        alert("Lengkapi semua data guru sebelum menyimpan.");
        return;
    }

    if (capturedImages.length < 5) {
        alert("Ambil 5 gambar pose terlebih dahulu.");
        return;
    }

    const formData = new FormData();
    formData.append("nama", nama);
    formData.append("ttl", ttl);
    formData.append("jenis_kelamin", jenisKelamin);
    formData.append("tahun_mulai_kerja", tahunMulaiKerja);

    for (let i = 0; i < 5; i++) {
        formData.append(`image_${i + 1}`, capturedImages[i], `pose_${i + 1}.jpg`);
    }

    try {
        const res = await fetch("/save_faces", {
            method: "POST",
            body: formData,
        });
        const result = await res.json();
        if (result.success) {
            statusDiv.textContent = "✅ Wajah berhasil disimpan ke dataset.";
            statusDiv.style.color = "green";

            // Reset form
            namaInput.value = "";
            document.getElementById("ttl").value = "";
            document.getElementById("jenis_kelamin").value = "";
            document.getElementById("tahun_mulai_kerja").value = "";
            capturedImages = [];
            previewContainer.innerHTML = "";
        } else {
            statusDiv.textContent = "❌ Gagal menyimpan: " + result.message;
            statusDiv.style.color = "red";
        }
    } catch (err) {
        console.error("Gagal kirim:", err);
        statusDiv.textContent = "❌ Gagal mengirim ke server.";
        statusDiv.style.color = "red";
    }
}


// Event Listener
captureBtn.addEventListener("click", captureImage);
saveBtn.addEventListener("click", submitImages);
stopCameraBtn.addEventListener("click", stopCamera);
startCamera();
