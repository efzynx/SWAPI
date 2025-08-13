#!/usr/bin/env python3
# swap_manager.py
import os
import shutil
import subprocess
import re

SUDO = "" if os.geteuid() == 0 else "sudo "

def run(cmd):
    p = subprocess.run(cmd, shell=True, text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return p.returncode, p.stdout.strip(), p.stderr.strip()

def find_cmd(name: str):
    # Cari di PATH dulu
    path = shutil.which(name)
    if path:
        return path
    # Cek lokasi umum (Debian/Arch)
    for d in ("/usr/sbin", "/sbin", "/usr/bin", "/bin"):
        cand = os.path.join(d, name)
        if os.path.exists(cand) and os.access(cand, os.X_OK):
            return cand
    return None

def parse_size_to_mib(s: str):
    s = s.strip().lower()
    m = re.match(r'^(\d+(?:\.\d+)?)(g|gb|gi|m|mb|mi)$', s)
    if not m:
        return None
    val = float(m.group(1))
    unit = m.group(2)[0]  # g atau m
    return int(val * 1024) if unit == 'g' else int(val)

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

    # Tambahan: tampilkan detail prioritas dari /proc/swaps kalau ada
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

    run(f"{SUDO} sed -i '\\#{path}#d' /etc/fstab")
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
            # Coba opsi -p (versi lama)
            code2, _, err2 = run(f"{SUDO} {swapon} -p {new_pri} {target}")
            if code2 != 0:
                print("❌ Gagal mengaktifkan dengan prioritas baru:", (err or err2))
                return
        print("✅ Prioritas runtime diubah.")
    else:
        print("⚠ 'swapon/swapoff' tidak ditemukan. Akan memperbarui konfigurasi permanen saja.")

    # Persist ke fstab kalau target bukan zram
    if "/zram" in target:
        print("ℹ ZRAM tidak dikonfigurasi via /etc/fstab. Untuk persist, atur di zram-generator (override.conf).")
    else:
        run(f"{SUDO} sed -i '\\#{re.escape(target)}#d' /etc/fstab")
        run(f"echo '{target} none swap defaults,pri={new_pri} 0 0' | {SUDO} tee -a /etc/fstab > /dev/null")
        print("✅ /etc/fstab diperbarui.")

def main():
    while True:
        print("""
===== SWAP MANAGER =====
1. Cek swap
2. Tambah swap file
3. Hapus swap file
4. Ubah prioritas swap
5. Keluar
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
            break
        else:
            print("❌ Pilihan tidak valid.")

if __name__ == "__main__":
    main()
