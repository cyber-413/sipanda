# SIPANDA - Sistem Pengumpulan Arsip dan Data

## Cara Install
1. Buat database lewat phpMyAdmin atau MySQL CLI dengan menjalankan `schema.sql`.
2. Atur konfigurasi database di `app.py` bagian `DB_CONFIG`.
3. Install package:
   ```bash
   pip install -r requirements.txt
   ```
4. Jalankan aplikasi:
   ```bash
   python app.py
   ```
5. Buka browser: `http://127.0.0.1:5000`

## Login Default
- Username: `admin`
- Password: `admin123`

## Fitur
- Landing page sebelum login.
- Login admin.
- Dashboard biru abu-abu seperti contoh.
- Kategori arsip: IJAZAH, KK, KTP, SK CPNS, SK JABATAN, SK KGB, SK PANGKAT, SK PNS, SKP.
- Tambah dan hapus folder unlimited di setiap kategori.
- Upload PDF, Word, Excel di dalam folder.
- File hanya bisa dilihat dan dihapus, tidak bisa diedit.
- Tanpa SQLAlchemy, memakai `mysql-connector-python`.
