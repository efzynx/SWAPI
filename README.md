# 🛠️ SWAP Manager — ZRAM & Swapfile Utility for Linux

**SWAP Manager** adalah script interaktif berbasis Bash untuk mengelola swap di Linux, mendukung:

* Pembuatan **swapfile** dengan ukuran dan prioritas custom
* Pembuatan **ZRAM** permanen (via systemd service)
* **Hybrid mode** (ZRAM + Swapfile) dengan pre-check anti-duplikat
* Resize, ubah prioritas, dan hapus swap secara mudah

Script ini cocok untuk pengguna yang ingin mengoptimalkan memori virtual di sistemnya, baik untuk server maupun desktop.

---

## ✨ Fitur Utama

* **Cek status swap** (`swapon` & `/proc/swaps`)
* **Tambah swapfile** dengan ukuran dan path custom
* **Hapus swapfile** (otomatis hapus dari `/etc/fstab`)
* **Ubah prioritas swap**
* **Resize swapfile** tanpa hapus manual
* **Setup Hybrid Mode**: ZRAM + Swapfile sekaligus
* **Hapus Hybrid** untuk mengembalikan konfigurasi seperti semula
* Pre-check agar tidak membuat ZRAM / swapfile ganda

---

## 📦 Instalasi

Clone repository ini:

```bash
git clone https://github.com/efzynx/swapi.git
cd swapi
chmod +x swap-manager.sh
```

---

## 🚀 Cara Menjalankan

Jalankan script:

```bash
./swap-manager.sh
```

Menu utama akan muncul:

```
===== SWAP MANAGER =====
1. Cek swap
2. Tambah swap file
3. Hapus swap file
4. Ubah prioritas swap
5. Resize swapfile
6. Setup hybrid otomatis (zram + swapfile)
7. Hapus hybrid
8. Keluar
```

---

## 📖 Contoh Penggunaan

### 1. Setup Hybrid Mode (ZRAM + Swapfile)

```
Pilih menu: 6
Ukuran ZRAM (mis. 2G, kosong=skip ZRAM): 1G
Path swapfile (default: /swapfile):
Ukuran swapfile (mis. 8G): 4G
Prioritas ZRAM (default 100):
Prioritas swapfile (default -1):
```

Output:

```
✅ ZRAM permanent 1G dibuat dengan prioritas 100
✅ Swapfile /swapfile siap (pri=-1)
✨ Hybrid selesai. ZRAM dan swapfile aktif & persist.
```

---

### 2. Resize Swapfile

```
Pilih menu: 5
Path swapfile: /swapfile
Ukuran baru (mis. 6G): 8G
✅ Swapfile berhasil di-resize ke 8G
```

---

### 3. Hapus Hybrid Mode

```
Pilih menu: 7
❌ ZRAM & swapfile dihapus, konfigurasi dikembalikan ke default
```

---

## ⚙️ Catatan Teknis

* **ZRAM** dibuat permanen via `/etc/systemd/system/zram.service`
* **Swapfile** dibuat permanen via entri di `/etc/fstab`
* Hybrid mode akan otomatis:

  * Menjalankan `mkswap` & `swapon`
  * Mengatur prioritas swap
  * Menghapus entri lama jika sudah ada
* Tested di:

  * Debian 12+
  * Arch Linux
  * Ubuntu 22.04+

---

## 📜 Lisensi

MIT License — Silakan gunakan, modifikasi, dan distribusikan dengan bebas.

---

## 👨‍💻 Kontribusi

Pull request & issue sangat terbuka.
Kalau ada bug atau ide fitur baru, silakan ajukan di tab **Issues**.
