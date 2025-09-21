document.addEventListener('DOMContentLoaded', function () {
    const button = document.getElementById('downloadExcelBtn');

    button.addEventListener('click', function () {
        const table = document.getElementById('rekapTable');
        let csvContent = "data:text/csv;charset=utf-8,";

        const rows = table.querySelectorAll("tr");
        rows.forEach(row => {
            let rowData = [];
            row.querySelectorAll("td, th").forEach(cell => {
                rowData.push(cell.innerText);
            });
            csvContent += rowData.join(",") + "\r\n";
        });

        const encodedUri = encodeURI(csvContent);
        const link = document.createElement("a");
        link.setAttribute("href", encodedUri);
        link.setAttribute("download", "rekap_absensi_guru.csv");
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    });
});
