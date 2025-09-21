const video = document.getElementById('video');
const canvas = document.getElementById('canvas');
const message = document.getElementById('message');

// Minta akses kamera
navigator.mediaDevices.getUserMedia({ video: true })
    .then((stream) => {
        video.srcObject = stream;
    })
    .catch((err) => {
        message.innerText = 'Gagal mengakses kamera: ' + err;
    });

function captureAndSend() {
    const context = canvas.getContext('2d');
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    const imageData = canvas.toDataURL('image/jpeg');

    fetch('/pindai_absensi', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: `image=${encodeURIComponent(imageData)}`
    })
    .then(response => {
        const contentType = response.headers.get("content-type");
        if (contentType && contentType.includes("application/json")) {
            return response.json();
        } else {
            throw new Error("Respon bukan JSON");
        }
    })
    .then(data => {
        message.innerText = data.message;
        message.style.color = data.success ? 'green' : 'red';
    })
    .catch(error => {
        console.error("Error:", error);
        message.innerText = 'Terjadi kesalahan: ' + error.message;
        message.style.color = 'red';
    });
}

