document.addEventListener('DOMContentLoaded', function () {
    const dataTag = document.getElementById('chart-data');
    const rawData = {
        labels: JSON.parse(dataTag.dataset.labels),
        dataHadir: JSON.parse(dataTag.dataset.hadir),
        dataBelumHadir: JSON.parse(dataTag.dataset.belumHadir),
        hariLibur: JSON.parse(dataTag.dataset.hariLibur)
    };

    // Dapatkan waktu Indonesia
    const tanggal = new Date().toLocaleString('id-ID', { timeZone: 'Asia/Jakarta' });
    const bulanSaatIni = new Date(tanggal).getMonth() + 1; // 1–12
    const semester = bulanSaatIni <= 6 ? '1' : '2';

    // Buat label bulan otomatis berdasarkan semester
    const bulanSemester1 = ['Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun'];
    const bulanSemester2 = ['Jul', 'Ags', 'Sep', 'Okt', 'Nov', 'Des'];
    const labels = semester === '1' ? bulanSemester1 : bulanSemester2;

    // Filter data hadir dan belum hadir berdasarkan semester (asumsinya index 0 = Jan)
    const startIdx = semester === '1' ? 0 : 6;
    const endIdx = semester === '1' ? 6 : 12;
    const dataHadir = rawData.dataHadir.slice(startIdx, endIdx);
    const dataBelumHadir = rawData.dataBelumHadir.slice(startIdx, endIdx);

    const ctx = document.getElementById('absenChart')?.getContext('2d');
    let absenChart;

    if (ctx) {
        absenChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Hadir',
                        data: dataHadir,
                        backgroundColor: '#3CB371',
                        borderRadius: 8,
                        barThickness: 12
                    },
                    {
                        label: 'Belum Hadir',
                        data: dataBelumHadir,
                        backgroundColor: '#FF6B6B',
                        borderRadius: 8,
                        barThickness: 12
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                layout: {
                    padding: { top: 20, bottom: 20 }
                },
                plugins: {
                    legend: {
                        position: 'top',
                        labels: {
                            font: {
                                size: 13,
                                family: 'Poppins'
                            }
                        }
                    },
                    tooltip: {
                        callbacks: {
                            label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y} orang`
                        },
                        backgroundColor: '#fff',
                        titleColor: '#000',
                        bodyColor: '#333',
                        borderColor: '#ccc',
                        borderWidth: 1
                    },
                    title: {
                        display: true,
                        text: `Grafik Kehadiran Guru Semester ${semester}`,
                        font: {
                            size: 16,
                            family: 'Poppins'
                        }
                    }
                },
                scales: {
                    x: {
                        ticks: {
                            font: { size: 12, family: 'Poppins' },
                            color: '#333'
                        },
                        grid: { display: false }
                    },
                    y: {
                        beginAtZero: true,
                        ticks: {
                            stepSize: 1,
                            font: { size: 12, family: 'Poppins' },
                            color: '#333'
                        },
                        grid: {
                            color: '#eee'
                        }
                    }
                }
            }
        });
    }

    // Tampilkan daftar hari libur
    const liburList = document.getElementById('daftar-libur');
    if (liburList && Array.isArray(rawData.hariLibur)) {
        liburList.innerHTML = rawData.hariLibur.length === 0
            ? '<li>Tidak ada hari libur terdaftar.</li>'
            : rawData.hariLibur.map(libur => `<li>${libur.tanggal} - ${libur.keterangan}</li>`).join('');
    }

    // Tombol download chart ke JPEG
    const downloadBtn = document.getElementById('downloadChartBtn');
    if (downloadBtn && absenChart) {
        downloadBtn.addEventListener('click', function () {
            const imageBase64 = absenChart.toBase64Image();
            const link = document.createElement('a');
            link.href = imageBase64;
            link.download = 'grafik_kehadiran_per_semester.jpeg';
            link.click();
        });
    }
});
