#!/usr/bin/env python3
# swap_manager.py — v1.2
# Fitur:
# 1) Cek swap (swapon -> fallback free -h) + detail /proc/swaps
# 2) Buat swapfile
# 3) Hapus swapfile
# 4) Ubah prioritas swap (runtime + persist fstab bila applicable)
# 5) Resize swapfile (pertahankan prioritas lama)
# 6) Setup hybrid otomatis (zram + swapfile) dengan prioritas

import os
import shutil
import subprocess
import re

# Bersihkan terminal saat start (opsional)
os.system('clear')

SUDO = "" if os.geteuid() == 0 else "sudo "

# -------------------- Util --------------------
def run(cmd):
    p = subprocess.run(cmd, shell=True, text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return p.returncode, p.stdout.strip(), p.stderr.strip()

def find_cmd(name: str):
    path = shutil.which(name)
    if path:
        return path
    for d in ("/usr/sbin", "/sbin", "/usr/bin", "/bin"):
        cand = os.path.join(d, name)
        if os.path.exists(cand) and os.access(cand, os.X_OK):
            return cand
    return None

def parse_size_to_bytes(s: str):
    s = s.strip().lower()
    m = re.match(r'^(\d+(?:\.\d+)?)(g|gb|gi|m|mb|mi|k|kb|ki)?$', s)
    if not m:
        return None
    val = float(m.group(1))
    unit = (m.group(2) or 'm')[0]  # default MiB
    if unit == 'g':
        return int(val * 1024 * 1024 * 1024)
    elif unit == 'm':
        return int(val * 1024 * 1024)
    elif unit == 'k':
        return int(val * 1024)
    else:
        return None

def parse_size_to_mib(s: str):
    b = parse_size_to_bytes(s)
    return int(round(b / (1024 * 1024))) if b is not None else None

# -------------------- Swap Info --------------------
def get_swaps_from_proc():
    swaps = []
    try:
        with open("/proc/swaps") as f:
            lines = f.read().strip().splitlines()
        for i, line in enumerate(lines):
            if i == 0:  # header
                continue
            parts = line.split()
            if len(parts) >= 5:
                swaps.append({
                    "name": parts[0],
                    "type": parts[1],
                    "size_kib": int(parts[2]),
                    "used_kib": int(parts[3]),
                    "prio": int(parts[4]),
                })
    except Exception:
        pass
    return swaps

def get_priority_for(path: str):
    # 1) coba dari /proc/swaps runtime
    for s in get_swaps_from_proc():
        if s['name'] == path:
            return s['prio']
    # 2) coba dari /etc/fstab persist
    try:
        with open('/etc/fstab') as f:
            for line in f:
                if line.strip().startswith('#'):
                    continue
                if path in line:
                    # cari pri=NUMBER dalam opsi
                    m = re.search(r'pri=(-?\d+)', line)
                    if m:
                        return int(m.group(1))
    except Exception:
        pass
    return None

# -------------------- Actions --------------------
def check_swap():
    swapon = find_cmd("swapon")
    if swapon:
        code, out, err = run(f"{swapon} --show")
        if out:
            print("\n=== Info Swap (swapon) ===")
            print(out)
        else:
            print("Tidak ada swap aktif (swapon).")
    else:
        print("\n⚠ 'swapon' tidak ditemukan, fallback ke 'free -h':")
        _, out, _ = run("free -h")
        print(out)

    swaps = get_swaps_from_proc()
    if swaps:
        print("\n=== Detail /proc/swaps ===")
        print("Filename\t\tType\tSize(MiB)\tUsed(MiB)\tPrio")
        for s in swaps:
            print(f"{s['name']}\t{s['type']}\t{int(s['size_kib']/1024)}\t\t{int(s['used_kib']/1024)}\t\t{s['prio']}")


def add_swap():
    path = (input("Path swapfile (default: /swapfile): ").strip() or "/swapfile")
    size_str = input("Ukuran (contoh 8G atau 4096M): ").strip()
    mib = parse_size_to_mib(size_str)
    if not mib:
        print("❌ Ukuran tidak valid. Contoh benar: 8G, 4096M")
        return

    print(f"\n[Membuat] {path} sebesar {size_str} ...")
    code, _, _ = run(f"{SUDO} fallocate -l {size_str} {path}")
    if code != 0:
        print("fallocate gagal, fallback ke dd (lebih lama)...")
        code, _, err = run(f"{SUDO} dd if=/dev/zero of={path} bs=1M count={mib} status=progress")
        if code != 0:
            print("❌ Gagal membuat swapfile:", err)
            return

    run(f"{SUDO} chmod 600 {path}")
    run(f"{SUDO} mkswap {path}")

    swapon = find_cmd("swapon")
    if swapon:
        run(f"{SUDO} {swapon} {path}")
        print("✅ Swapfile diaktifkan.")
    else:
        print("⚠ 'swapon' tidak ditemukan. Swap akan aktif setelah reboot jika ditambahkan ke fstab.")

    ans = input("Tambahkan ke /etc/fstab agar permanen? (y/n): ").strip().lower()
    if ans == "y":
        pri = input("Set priority? (mis. -1, kosong = tanpa pri): ").strip()
        opts = "defaults" + (f",pri={pri}" if pri else "")
        run(f"echo '{path} none swap {opts} 0 0' | {SUDO} tee -a /etc/fstab > /dev/null")
        print("✅ Ditambahkan ke /etc/fstab.")


def remove_swap():
    path = (input("Path swapfile yang dihapus (default: /swapfile): ").strip() or "/swapfile")
    print(f"\n[Hapus] {path} ...")
    swapoff = find_cmd("swapoff")
    if swapoff:
        run(f"{SUDO} {swapoff} {path}")
    else:
        run(f"{SUDO} swapoff {path}")  # best effort

    run(f"{SUDO} sed -i '\#{path}#d' /etc/fstab")
    run(f"{SUDO} rm -f {path}")
    print("✅ Swapfile dihapus & fstab dibersihkan.")


def set_swap_priority():
    swaps = get_swaps_from_proc()
    if not swaps:
        print("❌ Tidak ada swap aktif.")
        return

    print("\nSwap aktif:")
    for i, s in enumerate(swaps, 1):
        size_gib = s['size_kib'] / 1024 / 1024
        used_gib = s['used_kib'] / 1024 / 1024
        print(f"{i}. {s['name']} ({s['type']})  size≈{size_gib:.2f}GiB  used≈{used_gib:.2f}GiB  prio={s['prio']}")

    sel = input("Pilih nomor target: ").strip()
    if not sel.isdigit() or not (1 <= int(sel) <= len(swaps)):
        print("❌ Pilihan tidak valid.")
        return

    target = swaps[int(sel) - 1]['name']
    new_pri = input("Masukkan prioritas baru (mis. -1..100): ").strip()
    if new_pri == "":
        print("❌ Prioritas kosong.")
        return

    swapoff = find_cmd("swapoff")
    swapon = find_cmd("swapon")

    if swapon and swapoff:
        run(f"{SUDO} {swapoff} {target}")
        code, _, err = run(f"{SUDO} {swapon} --priority {new_pri} {target}")
        if code != 0:
            code2, _, err2 = run(f"{SUDO} {swapon} -p {new_pri} {target}")
            if code2 != 0:
                print("❌ Gagal mengaktifkan dengan prioritas baru:", (err or err2))
                return
        print("✅ Prioritas runtime diubah.")
    else:
        print("⚠ 'swapon/swapoff' tidak ditemukan. Akan memperbarui konfigurasi permanen saja.")

    if "/zram" in target:
        print("ℹ ZRAM tidak dikonfigurasi via /etc/fstab. Untuk persist, atur di zram-generator (override.conf).")
    else:
        run(f"{SUDO} sed -i '\#{re.escape(target)}#d' /etc/fstab")
        run(f"echo '{target} none swap defaults,pri={new_pri} 0 0' | {SUDO} tee -a /etc/fstab > /dev/null")
        print("✅ /etc/fstab diperbarui.")


# -------------------- NEW: Resize swapfile --------------------
def resize_swapfile():
    path = (input("Path swapfile yang ingin di-resize (default: /swapfile): ").strip() or "/swapfile")
    if not os.path.exists(path):
        print("❌ Swapfile tidak ditemukan.")
        return

    new_size = input("Ukuran baru (contoh 12G atau 6144M): ").strip()
    mib = parse_size_to_mib(new_size)
    if not mib:
        print("❌ Ukuran tidak valid.")
        return

    # simpan prioritas lama (runtime/fstab)
    old_pri = get_priority_for(path)

    print(f"\n[Resize] {path} -> {new_size}")
    swapoff = find_cmd("swapoff")
    if swapoff:
        run(f"{SUDO} {swapoff} {path}")
    else:
        run(f"{SUDO} swapoff {path}")

    # Resize menggunakan fallocate; bila gagal fallback dd (overwrite)
    code, _, _ = run(f"{SUDO} fallocate -l {new_size} {path}")
    if code != 0:
        print("fallocate gagal, fallback ke dd ...")
        code, _, err = run(f"{SUDO} dd if=/dev/zero of={path} bs=1M count={mib} status=progress")
        if code != 0:
            print("❌ Gagal resize:", err)
            return

    run(f"{SUDO} chmod 600 {path}")
    run(f"{SUDO} mkswap {path}")

    swapon = find_cmd("swapon")
    if swapon:
        if old_pri is not None:
            # pertahankan prioritas lama
            code, _, err = run(f"{SUDO} {swapon} --priority {old_pri} {path}")
            if code != 0:
                run(f"{SUDO} {swapon} -p {old_pri} {path}")
        else:
            run(f"{SUDO} {swapon} {path}")
        print("✅ Resize selesai & swapfile aktif kembali.")
    else:
        print("⚠ 'swapon' tidak ditemukan. Swap akan aktif setelah reboot.")

    # Update fstab: hapus baris lama & tulis ulang dengan pri lama jika ada
    run(f"{SUDO} sed -i '\#{re.escape(path)}#d' /etc/fstab")
    opts = "defaults" + (f",pri={old_pri}" if old_pri is not None else "")
    run(f"echo '{path} none swap {opts} 0 0' | {SUDO} tee -a /etc/fstab > /dev/null")
    print("✅ /etc/fstab diperbarui.")


# -------------------- NEW: Setup Hybrid (zram + swapfile) --------------------
def setup_hybrid():
    print("\n=== Setup Hybrid (ZRAM + Swapfile) ===")
    # Konfigurasi
    zr_size = input("Ukuran ZRAM (contoh 2G, 4G, kosong=skip zram setup): ").strip()
    sf_path = (input("Path swapfile (default: /swapfile): ").strip() or "/swapfile")
    sf_size = input("Ukuran swapfile (contoh 8G): ").strip()
    pri_zr = input("Prioritas ZRAM (default 100): ").strip() or "100"
    pri_sf = input("Prioritas swapfile (default -1): ").strip() or "-1"

    # 1) Setup/aktifkan ZRAM (runtime) jika user mengisi ukuran
    if zr_size:
        bytes_ = parse_size_to_bytes(zr_size)
        if not bytes_:
            print("❌ Ukuran ZRAM tidak valid.")
            return
        # pastikan modul zram
        run(f"{SUDO} modprobe zram")
        # Pakai zramctl kalau ada (lebih portable), else sysfs manual
        zramctl = find_cmd("zramctl")
        target_dev = "/dev/zram0"
        # Matikan kalau sudah aktif
        swapoff = find_cmd("swapoff")
        if swapoff:
            run(f"{SUDO} {swapoff} {target_dev}")
        # Allocate
        if zramctl:
            # create/find zram0
            run(f"{SUDO} {zramctl} --find --size {bytes_}")
        else:
            # Sysfs manual
            if os.path.exists("/sys/block/zram0/disksize"):
                run(f"echo {bytes_} | {SUDO} tee /sys/block/zram0/disksize > /dev/null")
            else:
                print("❌ Tidak menemukan /sys/block/zram0. ZRAM mungkin tidak tersedia pada kernel.")
                return
        # format & aktifkan dgn prioritas
        run(f"{SUDO} mkswap {target_dev}")
        swapon = find_cmd("swapon")
        if swapon:
            code, _, err = run(f"{SUDO} {swapon} --priority {pri_zr} {target_dev}")
            if code != 0:
                run(f"{SUDO} {swapon} -p {pri_zr} {target_dev}")
        print("✅ ZRAM aktif.")

        # Persist (best-effort) via zram-generator jika ada
        zr_gen = find_cmd("zram-generator") or (
            "/usr/lib/systemd/zram-generator" if os.path.exists("/usr/lib/systemd/zram-generator") else None
        )
        if zr_gen:
            run(f"{SUDO} mkdir -p /etc/systemd/zram-generator.conf.d")
            conf = f"""
[zram0]
zram-size = {int(bytes_/1024/1024)}
priorities = {pri_zr}
"""
            run(f"echo '{conf}' | {SUDO} tee /etc/systemd/zram-generator.conf.d/override.conf > /dev/null")
            run(f"{SUDO} systemctl daemon-reexec")
            print("✅ Konfigurasi zram-generator ditulis (persist).")
        else:
            print("ℹ zram-generator tidak ditemukan. Persist zram tidak dibuat (runtime only).")

    # 2) Setup swapfile dengan prioritas lebih rendah
    mib = parse_size_to_mib(sf_size)
    if not mib:
        print("❌ Ukuran swapfile tidak valid.")
        return

    # Buat/format/aktifkan swapfile
    if not os.path.exists(sf_path):
        print(f"[Membuat swapfile] {sf_path} sebesar {sf_size} ...")
        code, _, _ = run(f"{SUDO} fallocate -l {sf_size} {sf_path}")
        if code != 0:
            print("fallocate gagal, fallback ke dd ...")
            code, _, err = run(f"{SUDO} dd if=/dev/zero of={sf_path} bs=1M count={mib} status=progress")
            if code != 0:
                print("❌ Gagal membuat swapfile:", err)
                return
        run(f"{SUDO} chmod 600 {sf_path}")
    else:
        print(f"[Gunakan swapfile ada] {sf_path}")

    run(f"{SUDO} mkswap {sf_path}")
    swapon = find_cmd("swapon")
    if swapon:
        # aktifkan dengan prioritas
        code, _, err = run(f"{SUDO} {swapon} --priority {pri_sf} {sf_path}")
        if code != 0:
            run(f"{SUDO} {swapon} -p {pri_sf} {sf_path}")
        print("✅ Swapfile aktif (hybrid).")
    else:
        print("⚠ 'swapon' tidak ditemukan. Swapfile akan aktif setelah reboot.")

    # Persist fstab untuk swapfile
    run(f"{SUDO} sed -i '\#{re.escape(sf_path)}#d' /etc/fstab")
    run(f"echo '{sf_path} none swap defaults,pri={pri_sf} 0 0' | {SUDO} tee -a /etc/fstab > /dev/null")
    print("✅ /etc/fstab diperbarui untuk swapfile (persist).")

    print("\n✨ Hybrid selesai. ZRAM diprioritaskan lebih tinggi daripada swapfile (sesuai prioritas yang kamu set).")


# -------------------- Menu --------------------
def main():
    while True:
        print("""
===== SWAP MANAGER =====
1. Cek swap
2. Tambah swap file
3. Hapus swap file
4. Ubah prioritas swap
5. Resize swapfile
6. Setup hybrid otomatis (zram + swapfile)
7. Keluar
""")
        choice = input("Pilih menu: ").strip()
        if choice == "1":
            check_swap()
        elif choice == "2":
            add_swap()
        elif choice == "3":
            remove_swap()
        elif choice == "4":
            set_swap_priority()
        elif choice == "5":
            resize_swapfile()
        elif choice == "6":
            setup_hybrid()
        elif choice == "7":
            break
        else:
            print("❌ Pilihan tidak valid.")

if __name__ == "__main__":
    main()
