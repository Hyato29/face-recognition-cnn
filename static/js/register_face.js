document.addEventListener("DOMContentLoaded", function () {
  // Mengambil elemen dari HTML baru berdasarkan ID
  const video = document.getElementById("video");
  const canvas = document.getElementById("canvas");
  const captureBtn = document.getElementById("captureBtn");
  const saveBtn = document.getElementById("saveBtn");
  const previewContainer = document.getElementById("previewContainer");
  const cameraPlaceholder = document.getElementById("camera-placeholder");
  const captureCountSpan = document.getElementById("captureCount");
  const faceForm = document.getElementById("faceForm");
  const namaInput = document.getElementById("nama");

  // Mengambil URL dari atribut data-save-url di form HTML
  const saveUrl = faceForm.dataset.saveUrl;

  let capturedImages = []; // Array untuk menyimpan 5 gambar pose
  const MAX_CAPTURES = 5;

  // Fungsi untuk menyalakan kamera
  async function setupCamera() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: 640, height: 480 },
      });
      video.srcObject = stream;
      video.onloadedmetadata = () => {
        cameraPlaceholder.classList.add("hidden"); // Sembunyikan pesan "Mengaktifkan kamera..."
        captureBtn.disabled = false; // Aktifkan tombol "Ambil Gambar"
      };
    } catch (err) {
      console.error("Error accessing camera: ", err);
      cameraPlaceholder.innerHTML = `<p class="text-red-400">❌ Gagal akses kamera. Berikan izin.</p>`;
      Swal.fire(
        "Error",
        "Gagal mengakses kamera. Pastikan Anda memberikan izin pada browser.",
        "error"
      );
    }
  }

  // Fungsi untuk memperbarui tampilan UI (counter, panduan, tombol)
  function updateUI() {
    captureCountSpan.textContent = capturedImages.length;

    // Memberi tanda pada panduan pose yang sudah diambil
    for (let i = 1; i <= MAX_CAPTURES; i++) {
      const poseGuide = document.getElementById(`pose-${i}`);
      if (i <= capturedImages.length) {
        poseGuide.classList.add("border-cyan-400", "bg-cyan-900");
      } else {
        poseGuide.classList.remove("border-cyan-400", "bg-cyan-900");
      }
    }

    if (capturedImages.length >= MAX_CAPTURES) {
      captureBtn.disabled = true;
      captureBtn.textContent = "5 Pose Selesai";
      // Aktifkan tombol simpan jika nama sudah diisi
      if (namaInput.value.trim() !== "") {
        saveBtn.disabled = false;
      }
    } else {
      captureBtn.disabled = false;
      captureBtn.textContent = `Ambil Pose (${capturedImages.length + 1}/5)`;
      saveBtn.disabled = true;
    }
  }

  // Event listener untuk tombol "Ambil Gambar Pose"
  captureBtn.addEventListener("click", () => {
    if (capturedImages.length < MAX_CAPTURES) {
      const context = canvas.getContext("2d");
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      context.drawImage(video, 0, 0, canvas.width, canvas.height);

      // Mengubah gambar di canvas menjadi format file (blob)
      canvas.toBlob((blob) => {
        capturedImages.push(blob);

        // Menampilkan pratinjau gambar yang diambil
        const img = document.createElement("img");
        img.src = URL.createObjectURL(blob);
        img.className =
          "w-full h-auto object-cover rounded-lg border-2 border-gray-600";
        previewContainer.appendChild(img);

        updateUI();
      }, "image/jpeg");
    }
  });

  // Event listener untuk input nama, agar tombol simpan bisa aktif
  namaInput.addEventListener("input", () => {
    if (
      namaInput.value.trim() !== "" &&
      capturedImages.length >= MAX_CAPTURES
    ) {
      saveBtn.disabled = false;
    } else {
      saveBtn.disabled = true;
    }
  });

  // Event listener untuk tombol "Simpan Dataset"
  saveBtn.addEventListener("click", async () => {
    if (namaInput.value.trim() === "") {
      Swal.fire("Validasi Gagal", "Nama guru tidak boleh kosong.", "warning");
      return;
    }

    // Tampilkan notifikasi loading
    Swal.fire({
      title: "Menyimpan Data...",
      text: "Mohon tunggu, data dan wajah sedang diunggah.",
      allowOutsideClick: false,
      didOpen: () => {
        Swal.showLoading();
      },
    });

    const formData = new FormData(faceForm);
    capturedImages.forEach((blob, index) => {
      formData.append(`image_${index + 1}`, blob, `pose_${index + 1}.jpeg`);
    });

    try {
      // Mengirim data ke server menggunakan URL dari HTML
      const response = await fetch(saveUrl, {
        method: "POST",
        body: formData,
      });
      const result = await response.json();

      // Menampilkan notifikasi hasil dari server
      if (result.success) {
        Swal.fire("Berhasil!", result.message, "success").then(() => {
          window.location.reload(); // Muat ulang halaman setelah berhasil
        });
      } else {
        Swal.fire(
          "Gagal!",
          result.message || "Terjadi kesalahan saat menyimpan.",
          "error"
        );
      }
    } catch (error) {
      console.error("Error:", error);
      Swal.fire("Error Server", "Tidak dapat terhubung ke server.", "error");
    }
  });

  // Memulai kamera dan menginisialisasi UI saat halaman dimuat
  setupCamera();
  updateUI();
});
