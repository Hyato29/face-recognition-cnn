function togglePassword() {
    const passwordField = document.getElementById('password');
    const toggleBtn = document.querySelector('.toggle-password');
    if (passwordField.type === "password") {
        passwordField.type = "text";
        toggleBtn.textContent = "🙈 Sembunyikan";
    } else {
        passwordField.type = "password";
        toggleBtn.textContent = "👁️ Tampilkan";
    }
}
