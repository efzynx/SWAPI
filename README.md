# 🛠️ SWAPI | SWAP Manager — ZRAM & Swapfile Utility for Linux

**SWAP Manager** adalah script interaktif berbasis Bash untuk mengelola swap di Linux, mendukung:
- Pembuatan **swapfile** dengan ukuran dan prioritas custom
- Pembuatan **ZRAM** permanen (via systemd service)
- **Hybrid mode** (ZRAM + Swapfile) dengan pre-check anti-duplikat
- Resize, ubah prioritas, dan hapus swap secara mudah

Script ini cocok untuk pengguna yang ingin mengoptimalkan memori virtual di sistemnya, baik untuk server maupun desktop.

---

## ✨ Fitur Utama

- **Cek status swap** (`swapon` & `/proc/swaps`)
- **Tambah swapfile** dengan ukuran dan path custom
- **Hapus swapfile** (otomatis hapus dari `/etc/fstab`)
- **Ubah prioritas swap**
- **Resize swapfile** tanpa hapus manual
- **Setup Hybrid Mode**: ZRAM + Swapfile sekaligus
- **Hapus Hybrid** untuk mengembalikan konfigurasi seperti semula
- Pre-check agar tidak membuat ZRAM / swapfile ganda

---

## 📦 Instalasi

Clone repository ini:

```bash
git clone https://github.com/efzynx/swapi.git
cd swap-manager
chmod +x swap-manager.sh
