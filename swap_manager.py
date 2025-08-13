#!/usr/bin/env python3
import subprocess
import os

SWAP_FILE_PATH = "/swapfile"

def run_cmd(cmd):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.stdout.strip()

def check_swap():
    print("\n[INFO] Cek swap aktif...\n")
    output = run_cmd("swapon --show")
    if not output:
        print("❌ Tidak ada swap aktif.")
        return
    print(output)

def add_swap_file():
    if os.path.exists(SWAP_FILE_PATH):
        print(f"❌ Swap file {SWAP_FILE_PATH} sudah ada!")
        return
    
    size = input("Masukkan ukuran swap file (contoh: 8G, 4G): ").strip()
    print(f"[INFO] Membuat swap file {SWAP_FILE_PATH} sebesar {size} ...")
    run_cmd(f"sudo fallocate -l {size} {SWAP_FILE_PATH} || sudo dd if=/dev/zero of={SWAP_FILE_PATH} bs=1M count={int(size[:-1])*1024} status=progress")
    run_cmd(f"sudo chmod 600 {SWAP_FILE_PATH}")
    run_cmd(f"sudo mkswap {SWAP_FILE_PATH}")
    run_cmd(f"sudo swapon {SWAP_FILE_PATH}")
    run_cmd(f"echo '{SWAP_FILE_PATH} none swap defaults 0 0' | sudo tee -a /etc/fstab")
    print("✅ Swap file berhasil dibuat dan diaktifkan.")

def remove_swap_file():
    if not os.path.exists(SWAP_FILE_PATH):
        print(f"❌ Swap file {SWAP_FILE_PATH} tidak ditemukan.")
        return
    
    print(f"[INFO] Menonaktifkan dan menghapus swap file {SWAP_FILE_PATH} ...")
    run_cmd(f"sudo swapoff {SWAP_FILE_PATH}")
    run_cmd(f"sudo sed -i '\\#{SWAP_FILE_PATH}#d' /etc/fstab")
    run_cmd(f"sudo rm -f {SWAP_FILE_PATH}")
    print("✅ Swap file berhasil dihapus.")

def set_swap_priority():
    if not os.path.exists(SWAP_FILE_PATH):
        print(f"❌ Swap file {SWAP_FILE_PATH} tidak ditemukan.")
        return
    
    priority = input("Masukkan prioritas swap (-1 sampai 100, default 0): ").strip()
    run_cmd(f"sudo swapoff {SWAP_FILE_PATH}")
    run_cmd(f"sudo swapon --priority {priority} {SWAP_FILE_PATH}")
    run_cmd(f"sudo sed -i '\\#{SWAP_FILE_PATH}#d' /etc/fstab")
    run_cmd(f"echo '{SWAP_FILE_PATH} none swap defaults,pri={priority} 0 0' | sudo tee -a /etc/fstab")
    print(f"✅ Prioritas swap file diubah menjadi {priority}.")

def main():
    while True:
        print("""
==== Swap Manager ====
1. Cek swap aktif
2. Tambah swap file
3. Hapus swap file
4. Ubah prioritas swap file
5. Keluar
""")
        choice = input("Pilih menu: ").strip()
        if choice == "1":
            check_swap()
        elif choice == "2":
            add_swap_file()
        elif choice == "3":
            remove_swap_file()
        elif choice == "4":
            set_swap_priority()
        elif choice == "5":
            print("Keluar...")
            break
        else:
            print("❌ Pilihan tidak valid!")

if __name__ == "__main__":
    main()
