Panduan Penggunaan XipserCloud Panel V3 Final
Panel ini telah diperbarui untuk menggunakan Host 0.0.0.0 agar dapat diakses dari jaringan lokal (192.168.x.x).
A. Langkah Menjalankan Server (Wajib)
 * Pindah ke Direktori: Pastikan Anda berada di direktori yang sama dengan semua 6 file di atas.
   cd XipserCloudV2

 * Kunci Layar: (Opsional, tapi disarankan)
   termux-wake-lock

 * Jalankan Server:
   python server_app.py

B. Langkah Akses Panel (Penting!)
Karena server sekarang berjalan di 0.0.0.0, Anda harus menggunakan IP lokal Anda.
 * Cek IP Lokal Anda (di Termux):
   Saat server berjalan, buka sesi Termux baru (swipe dari kiri, pilih NEW SESSION) dan jalankan:
   ip addr show wlan0 | grep 'inet '

   Anda akan mendapatkan IP seperti 192.168.1.100/24. Ambil IP tanpa /24.
 * Akses di Browser:
   Buka browser di ponsel/PC Anda dan masukkan:
   http://[IP_YANG_ANDA_TEMUKAN]:8080

   Contoh: http://192.168.1.100:8080
C. Fungsi Nyata Panel
 * Kontrol Layanan: Menggunakan perintah Termux/Linux nyata (pkill dan menjalankan binari nginx, mysqld_safe, php-fpm).
 * MariaDB CLI: Menggunakan klien mysql nyata yang terinstal di Termux.
 * Firewall (iptables): Langsung mengeksekusi perintah iptables di sistem Anda.
 * Nginx Deploy: Membuat file konfigurasi Nginx nyata di $PREFIX/etc/nginx/sites-enabled/ dan memuat ulang Nginx.
Jika Anda masih mengalami error koneksi: Silakan instal pkg install termux-api dan jalankan termux-api-permission untuk memastikan izin jaringan sudah diberikan.
