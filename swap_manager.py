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

# ---------- Helpers untuk deteksi swap yang ada ----------
def classify_existing_swaps():
    """Kembalikan dict: {'zram': [paths], 'files': [paths], 'parts': [paths]} dari /proc/swaps"""
    zram, files, parts = [], [], []
    for s in get_swaps_from_proc():
        name = s['name']
        typ = s['type'].lower()
        if 'zram' in name:
            zram.append(name)
        elif typ == 'file':
            files.append(name)
        else:
            parts.append(name)
    return {'zram': zram, 'files': files, 'parts': parts}

def pick_from_list(title, items):
    """Pilih satu item dari list, return path terpilih atau None kalau batal."""
    if not items:
        return None
    print(f"\n{title}")
    for i, v in enumerate(items, 1):
        print(f"{i}. {v}")
    print("0. Batal")
    sel = input("Pilih: ").strip()
    if sel == "0":
        return None
    if sel.isdigit() and 1 <= int(sel) <= len(items):
        return items[int(sel) - 1]
    print("❌ Pilihan tidak valid.")
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

    run(f"{SUDO} sed -i '#{path}#d' /etc/fstab")
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
        run(f"{SUDO} sed -i '#{re.escape(target)}#d' /etc/fstab")
        run(f"echo '{target} none swap defaults,pri={new_pri} 0 0' | {SUDO} tee -a /etc/fstab > /dev/null")
        print("✅ /etc/fstab diperbarui.")


# -------------------- Resize swapfile --------------------
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
    run(f"{SUDO} sed -i '#{re.escape(path)}#d' /etc/fstab")
    opts = "defaults" + (f",pri={old_pri}" if old_pri is not None else "")
    run(f"echo '{path} none swap {opts} 0 0' | {SUDO} tee -a /etc/fstab > /dev/null")
    print("✅ /etc/fstab diperbarui.")
    

def resize_zram(dev="/dev/zram0", new_size_str=None):
    """Resize zram device (default /dev/zram0) sambil pertahankan prioritas."""
    if new_size_str is None:
        new_size_str = input(f"Ukuran ZRAM baru untuk {dev} (mis. 4G): ").strip()
    bytes_ = parse_size_to_bytes(new_size_str)
    if not bytes_:
        print("❌ Ukuran tidak valid.")
        return

    old_pri = get_priority_for(dev)

    # Matikan swap ZRAM
    swapoff = find_cmd("swapoff")
    if swapoff:
        run(f"{SUDO} {swapoff} {dev}")
    else:
        run(f"{SUDO} swapoff {dev}")

    # Resize via zramctl kalau ada; kalau tidak, via sysfs
    zramctl = find_cmd("zramctl")
    if zramctl:
        # reset dulu kalau perlu
        run(f"{SUDO} {zramctl} -r {dev}")
        # allocate ulang dengan size baru
        code, out, err = run(f"{SUDO} {zramctl} --find --size {bytes_}")
        if code != 0:
            print("❌ Gagal set size zram via zramctl:", err)
            return
        # Cari device yang dipakai (stdout biasanya mengembalikan dev baru, fallback ke dev lama)
        new_dev = out.strip().splitlines()[-1] if out.strip() else dev
        dev = new_dev
    else:
        # sysfs fallback
        if not os.path.exists(f"/sys/block/{os.path.basename(dev)}/disksize"):
            print("❌ Tidak menemukan sysfs zram. Kernel mungkin tidak mendukung.")
            return
        run(f"echo {bytes_} | {SUDO} tee /sys/block/{os.path.basename(dev)}/disksize > /dev/null")

    # format & aktifkan lagi
    run(f"{SUDO} mkswap {dev}")
    swapon = find_cmd("swapon")
    if swapon:
        if old_pri is not None:
            code, _, err = run(f"{SUDO} {swapon} --priority {old_pri} {dev}")
            if code != 0:
                run(f"{SUDO} {swapon} -p {old_pri} {dev}")
        else:
            run(f"{SUDO} {swapon} {dev}")
        print("✅ ZRAM di-resize & aktif kembali.")
    else:
        print("⚠ 'swapon' tidak ditemukan. ZRAM akan aktif setelah reboot.")

    # Persist pakai zram-generator kalau ada
    zr_gen = find_cmd("zram-generator") or ("/usr/lib/systemd/zram-generator"
                                            if os.path.exists("/usr/lib/systemd/zram-generator") else None)
    if zr_gen:
        mib = int(bytes_ / 1024 / 1024)
        pri = old_pri if old_pri is not None else 100
        run(f"{SUDO} mkdir -p /etc/systemd/zram-generator.conf.d")
        conf = f"[{os.path.basename(dev)}]\nzram-size = {mib}\npriorities = {pri}\n"
        run(f"echo '{conf}' | {SUDO} tee /etc/systemd/zram-generator.conf.d/override.conf > /dev/null")
        run(f"{SUDO} systemctl daemon-reexec")
        print("✅ Persist zram-generator diperbarui.")
    else:
        print("ℹ zram-generator tidak ada; perubahan ZRAM hanya runtime.")



# -------------------- Setup Hybrid (zram + swapfile) --------------------
def setup_hybrid():
    print("\n=== Setup Hybrid (ZRAM + Swapfile) — dengan pre-check anti double ===")

    # Cek yang sudah aktif
    existing = classify_existing_swaps()
    has_zr = bool(existing['zram'])
    has_sf = bool(existing['files'])

    if has_zr or has_sf:
        print("\nDitemukan swap aktif:")
        if has_zr:
            print(f"- ZRAM : {', '.join(existing['zram'])}")
        if has_sf:
            print(f"- Files: {', '.join(existing['files'])}")

        print("\nApa yang ingin kamu lakukan?")
        print("1) Buat baru (double) — tetap pertahankan yang lama")
        print("2) Hapus yang lama, lalu buat baru")
        print("3) Edit/Resize yang ada")
        print("4) Batal")
        choice = input("Pilih: ").strip()

        if choice == "4":
            return

        # --- Opsi 3: Resize/edit langsung (sub-menu) ---
        if choice == "3":
            # Pilih resize apa
            print("\nApa yang ingin di-resize?")
            opts = []
            if has_zr: opts.append("zram")
            if has_sf: opts.append("swapfile")
            for i, o in enumerate(opts, 1):
                print(f"{i}) {o}")
            print("0) Batal")
            sel = input("Pilih: ").strip()
            if sel == "0":
                return
            if not sel.isdigit() or not (1 <= int(sel) <= len(opts)):
                print("❌ Pilihan tidak valid.")
                return
            target = opts[int(sel) - 1]

            if target == "zram":
                dev = pick_from_list("Pilih device ZRAM:", existing['zram'])
                if dev:
                    resize_zram(dev)
            else:
                path = pick_from_list("Pilih swapfile:", existing['files'])
                if path:
                    # Reuse fungsi resize swapfile
                    def _resize_inline(p):
                        nonlocal path
                        path = p
                        # Minta ukuran baru di sini supaya inline
                        new_size = input(f"Ukuran baru untuk {path} (mis. 12G): ").strip()
                        # Panggil resize_swapfile tapi override input
                        # (duplikasi logic minimal dengan memanfaatkan fungsi yang ada)
                        # == Begin mini-wrapper ==
                        old_pri = get_priority_for(path)
                        swapoff = find_cmd("swapoff")
                        if swapoff:
                            run(f"{SUDO} {swapoff} {path}")
                        else:
                            run(f"{SUDO} swapoff {path}")
                        mib = parse_size_to_mib(new_size)
                        if not mib:
                            print("❌ Ukuran tidak valid.")
                            return
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
                                code, _, err = run(f"{SUDO} {swapon} --priority {old_pri} {path}")
                                if code != 0:
                                    run(f"{SUDO} {swapon} -p {old_pri} {path}")
                            else:
                                run(f"{SUDO} {swapon} {path}")
                            print("✅ Resize selesai & swapfile aktif kembali.")
                        else:
                            print("⚠ 'swapon' tidak ditemukan. Swap akan aktif setelah reboot.")
                        run(f"{SUDO} sed -i '#{re.escape(path)}#d' /etc/fstab")
                        opts = "defaults" + (f",pri={old_pri}" if old_pri is not None else "")
                        run(f"echo '{path} none swap {opts} 0 0' | {SUDO} tee -a /etc/fstab > /dev/null")
                        print("✅ /etc/fstab diperbarui.")
                        # == End mini-wrapper ==

                    _resize_inline(path)
            return

        # --- Opsi 2: Hapus yang lama dulu ---
        if choice == "2":
            # Hapus semua zram yang aktif
            if has_zr:
                swapoff = find_cmd("swapoff")
                zramctl = find_cmd("zramctl")
                for dev in existing['zram']:
                    if swapoff: run(f"{SUDO} {swapoff} {dev}")
                    else: run(f"{SUDO} swapoff {dev}")
                    if zramctl:
                        run(f"{SUDO} {zramctl} -r {dev}")
                    else:
                        # sysfs reset
                        if os.path.exists(f"/sys/block/{os.path.basename(dev)}/reset"):
                            run(f"echo 1 | {SUDO} tee /sys/block/{os.path.basename(dev)}/reset > /dev/null")
            # Hapus semua swapfile
            if has_sf:
                for path in existing['files']:
                    swapoff = find_cmd("swapoff")
                    if swapoff: run(f"{SUDO} {swapoff} {path}")
                    else: run(f"{SUDO} swapoff {path}")
                    run(f"{SUDO} sed -i '#{re.escape(path)}#d' /etc/fstab")
                    run(f"{SUDO} rm -f {path}")
            print("✅ Swap/ZRAM lama dibersihkan. Lanjut buat hybrid baru...")

        # --- Opsi 1: Buat baru (double) → cukup lanjut ke pembuatan baru di bawah ---
        # (tidak menghapus yang lama)
    else:
        print("Tidak ada swap aktif. Membuat hybrid baru dari nol...")

    # ====== Pembuatan hybrid baru (atau tambahan kalau pilih opsi 1) ======
    zr_size = input("Ukuran ZRAM (mis. 2G, kosong=skip ZRAM): ").strip()
    sf_path_default = "/swapfile2" if os.path.exists("/swapfile") else "/swapfile"
    sf_path = (input(f"Path swapfile (default: {sf_path_default}): ").strip() or sf_path_default)
    sf_size = input("Ukuran swapfile (mis. 8G): ").strip()
    pri_zr = input("Prioritas ZRAM (default 100): ").strip() or "100"
    pri_sf = input("Prioritas swapfile (default -1): ").strip() or "-1"

    # 1) ZRAM (opsional)
    if zr_size:
        bytes_ = parse_size_to_bytes(zr_size)
        if not bytes_:
            print("❌ Ukuran ZRAM tidak valid.")
            return
        run(f"{SUDO} modprobe zram")
        zramctl = find_cmd("zramctl")
        target_dev = "/dev/zram0"
        if zramctl:
            # cari device free
            code, out, err = run(f"{SUDO} {zramctl} --find --size {bytes_}")
            if code != 0:
                print("❌ Gagal alokasikan zram:", err)
                return
            target_dev = out.strip().splitlines()[-1] if out.strip() else target_dev
        else:
            # sysfs manual hanya aman untuk zram0
            if not os.path.exists("/sys/block/zram0/disksize"):
                print("❌ sysfs zram tidak ditemukan.")
                return
            run(f"echo {bytes_} | {SUDO} tee /sys/block/zram0/disksize > /dev/null")
        run(f"{SUDO} mkswap {target_dev}")
        swapon = find_cmd("swapon")
        if swapon:
            code, _, err = run(f"{SUDO} {swapon} --priority {pri_zr} {target_dev}")
            if code != 0:
                run(f"{SUDO} {swapon} -p {pri_zr} {target_dev}")
        print(f"✅ ZRAM aktif di {target_dev}.")

        # Persist via zram-generator bila ada
        zr_gen = find_cmd("zram-generator") or ("/usr/lib/systemd/zram-generator"
                                                if os.path.exists("/usr/lib/systemd/zram-generator") else None)
        if zr_gen:
            run(f"{SUDO} mkdir -p /etc/systemd/zram-generator.conf.d")
            conf = f"[{os.path.basename(target_dev)}]\nzram-size = {int(bytes_/1024/1024)}\npriorities = {pri_zr}\n"
            run(f"echo '{conf}' | {SUDO} tee /etc/systemd/zram-generator.conf.d/override.conf > /dev/null")
            run(f"{SUDO} systemctl daemon-reexec")
            print("✅ Persist zram-generator ditulis.")

    # 2) Swapfile wajib (hybrid)
    mib = parse_size_to_mib(sf_size)
    if not mib:
        print("❌ Ukuran swapfile tidak valid.")
        return
    if not os.path.exists(sf_path):
        print(f"[Membuat swapfile] {sf_path} sebesar {sf_size} ...")
        code, _, _ = run(f"{SUDO} fallocate -l {sf_size} {sf_path}")
        if code != 0:
            print("fallocate gagal, fallback dd ...")
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
        code, _, err = run(f"{SUDO} {swapon} --priority {pri_sf} {sf_path}")
        if code != 0:
            run(f"{SUDO} {swapon} -p {pri_sf} {sf_path}")
        print("✅ Swapfile aktif.")
    else:
        print("⚠ 'swapon' tidak ditemukan. Swapfile akan aktif setelah reboot.")

    # Persist fstab
    run(f"{SUDO} sed -i '#{re.escape(sf_path)}#d' /etc/fstab")
    run(f"echo '{sf_path} none swap defaults,pri={pri_sf} 0 0' | {SUDO} tee -a /etc/fstab > /dev/null")
    print("✅ /etc/fstab diperbarui. Hybrid set!")


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
