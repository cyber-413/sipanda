import os
import uuid
from functools import wraps
from urllib.parse import urlparse

from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory, abort
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import mysql.connector
from mysql.connector import Error


app = Flask(__name__)

app.secret_key = os.getenv("SECRET_KEY", "sipanda_secret_key_ganti_bebas_12345")


def get_db_config():
    mysql_url = os.getenv("MYSQL_URL")

    if mysql_url:
        parsed = urlparse(mysql_url)
        return {
            "host": parsed.hostname,
            "port": parsed.port or 3306,
            "user": parsed.username,
            "password": parsed.password,
            "database": parsed.path.lstrip("/") or "railway",
        }

    return {
        "host": os.getenv("MYSQLHOST"),
        "port": int(os.getenv("MYSQLPORT", 3306)),
        "user": os.getenv("MYSQLUSER"),
        "password": os.getenv("MYSQLPASSWORD"),
        "database": os.getenv("MYSQLDATABASE", "railway"),
    }


DB_CONFIG = get_db_config()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024

ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "xls", "xlsx"}

CATEGORY_SEED = [
    ("ijazah", "IJAZAH", 1),
    ("kk", "KK", 2),
    ("ktp", "KTP", 3),
    ("sk-cpns", "SK CPNS", 4),
    ("sk-jabatan", "SK JABATAN", 5),
    ("sk-kgb", "SK KGB (KENAIKAN GAJI BERKALA)", 6),
    ("sk-pangkat", "SK PANGKAT", 7),
    ("sk-pns", "SK PNS", 8),
    ("skp", "SKP", 9),
]


def db():
    return mysql.connector.connect(**DB_CONFIG)


def query(sql, params=None, fetchone=False, fetchall=False, commit=False):
    conn = db()
    cur = conn.cursor(dictionary=True)
    cur.execute(sql, params or ())

    data = None

    if fetchone:
        data = cur.fetchone()

    if fetchall:
        data = cur.fetchall()

    if commit:
        conn.commit()
        data = cur.lastrowid

    cur.close()
    conn.close()

    return data


def init_database():
    try:
        missing = []
        for key in ["host", "user", "password", "database"]:
            if not DB_CONFIG.get(key):
                missing.append(key)

        if missing:
            print("Database config missing:", missing)
            print("Current DB_CONFIG:", {
                "host": DB_CONFIG.get("host"),
                "port": DB_CONFIG.get("port"),
                "user": DB_CONFIG.get("user"),
                "database": DB_CONFIG.get("database"),
                "password": "SET" if DB_CONFIG.get("password") else None,
            })
            return

        conn = db()
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                username VARCHAR(50) NOT NULL UNIQUE,
                password VARCHAR(255) NOT NULL,
                role ENUM('admin','pegawai') DEFAULT 'admin',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id INT AUTO_INCREMENT PRIMARY KEY,
                slug VARCHAR(80) NOT NULL UNIQUE,
                name VARCHAR(150) NOT NULL,
                sort_order INT NOT NULL DEFAULT 0
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS folders (
                id INT AUTO_INCREMENT PRIMARY KEY,
                category_id INT NOT NULL,
                name VARCHAR(150) NOT NULL,
                created_by INT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_folders_category
                    FOREIGN KEY (category_id) REFERENCES categories(id)
                    ON DELETE CASCADE,
                CONSTRAINT fk_folders_user
                    FOREIGN KEY (created_by) REFERENCES users(id)
                    ON DELETE SET NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS files (
                id INT AUTO_INCREMENT PRIMARY KEY,
                folder_id INT NOT NULL,
                original_name VARCHAR(255) NOT NULL,
                stored_name VARCHAR(255) NOT NULL,
                mime_type VARCHAR(120) NULL,
                file_size BIGINT DEFAULT 0,
                uploaded_by INT NULL,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_files_folder
                    FOREIGN KEY (folder_id) REFERENCES folders(id)
                    ON DELETE CASCADE,
                CONSTRAINT fk_files_user
                    FOREIGN KEY (uploaded_by) REFERENCES users(id)
                    ON DELETE SET NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS password_resets (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                token VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_password_resets_user
                    FOREIGN KEY (user_id) REFERENCES users(id)
                    ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)

        cur.executemany("""
            INSERT IGNORE INTO categories (slug, name, sort_order)
            VALUES (%s, %s, %s)
        """, CATEGORY_SEED)

        conn.commit()
        cur.close()
        conn.close()

        admin = query(
            "SELECT id FROM users WHERE username=%s",
            ("admin",),
            fetchone=True
        )

        if not admin:
            query(
                "INSERT INTO users(name, username, password, role) VALUES(%s,%s,%s,%s)",
                (
                    "Administrator",
                    "admin",
                    generate_password_hash("admin123"),
                    "admin"
                ),
                commit=True
            )

        print("Database initialized successfully.")

    except Error as e:
        print("Database error:", e)


@app.context_processor
def inject_sidebar():
    try:
        cats = query("SELECT * FROM categories ORDER BY sort_order ASC", fetchall=True) or []
    except Exception:
        cats = []
    return dict(sidebar_categories=cats)


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Silakan login terlebih dahulu.", "warning")
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = query(
            "SELECT * FROM users WHERE username=%s",
            (username,),
            fetchone=True
        )

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["name"] = user["name"]
            session["role"] = user["role"]

            flash("Login berhasil.", "success")
            return redirect(url_for("dashboard"))

        flash("Username atau password salah.", "danger")

    return render_template("login.html")


@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        new_password = request.form.get("new_password")
        confirm_password = request.form.get("confirm_password")

        user = query(
            "SELECT * FROM users WHERE username=%s",
            (username,),
            fetchone=True
        )

        if not user:
            flash("Username tidak ditemukan.", "danger")
            return redirect(url_for("reset_password"))

        if new_password != confirm_password:
            flash("Konfirmasi password tidak cocok.", "danger")
            return redirect(url_for("reset_password"))

        hashed_password = generate_password_hash(new_password)

        query(
            "UPDATE users SET password=%s WHERE id=%s",
            (hashed_password, user["id"]),
            commit=True
        )

        flash("Password berhasil direset. Silakan login.", "success")
        return redirect(url_for("login"))

    return render_template("reset_password.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Berhasil logout.", "success")
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    stats = {
        "folders": query("SELECT COUNT(*) total FROM folders", fetchone=True)["total"],
        "files": query("SELECT COUNT(*) total FROM files", fetchone=True)["total"],
        "categories": query("SELECT COUNT(*) total FROM categories", fetchone=True)["total"],
        "users": query("SELECT COUNT(*) total FROM users", fetchone=True)["total"],
    }

    recent = query("""
        SELECT f.*, fo.name folder_name, c.name category_name
        FROM files f
        JOIN folders fo ON fo.id = f.folder_id
        JOIN categories c ON c.id = fo.category_id
        ORDER BY f.uploaded_at DESC
        LIMIT 8
    """, fetchall=True)

    return render_template("dashboard.html", stats=stats, recent=recent)


@app.route("/category/<slug>", methods=["GET", "POST"])
@login_required
def category(slug):
    cat = query("SELECT * FROM categories WHERE slug=%s", (slug,), fetchone=True)

    if not cat:
        abort(404)

    if request.method == "POST":
        name = request.form.get("folder_name", "").strip()

        if name:
            query(
                "INSERT INTO folders(category_id, name, created_by) VALUES(%s,%s,%s)",
                (cat["id"], name, session["user_id"]),
                commit=True
            )
            flash("Folder berhasil ditambahkan.", "success")

        return redirect(url_for("category", slug=slug))

    folders = query("""
        SELECT fo.*, COUNT(fi.id) total_files
        FROM folders fo
        LEFT JOIN files fi ON fi.folder_id = fo.id
        WHERE fo.category_id = %s
        GROUP BY fo.id
        ORDER BY fo.created_at DESC
    """, (cat["id"],), fetchall=True)

    return render_template("category.html", cat=cat, folders=folders)


@app.route("/folder/<int:folder_id>", methods=["GET", "POST"])
@login_required
def folder_detail(folder_id):
    folder = query("""
        SELECT fo.*, c.slug category_slug, c.name category_name
        FROM folders fo
        JOIN categories c ON c.id = fo.category_id
        WHERE fo.id = %s
    """, (folder_id,), fetchone=True)

    if not folder:
        abort(404)

    if request.method == "POST":
        file = request.files.get("file")

        if file and file.filename and allowed_file(file.filename):
            original = secure_filename(file.filename)
            ext = original.rsplit(".", 1)[1].lower()
            stored = f"{uuid.uuid4().hex}.{ext}"

            filepath = os.path.join(app.config["UPLOAD_FOLDER"], stored)
            file.save(filepath)

            size = os.path.getsize(filepath)

            query("""
                INSERT INTO files(
                    folder_id,
                    original_name,
                    stored_name,
                    mime_type,
                    file_size,
                    uploaded_by
                )
                VALUES(%s,%s,%s,%s,%s,%s)
            """, (
                folder_id,
                original,
                stored,
                file.mimetype,
                size,
                session["user_id"]
            ), commit=True)

            flash("File berhasil diupload.", "success")
        else:
            flash("File harus Word, Excel, atau PDF.", "danger")

        return redirect(url_for("folder_detail", folder_id=folder_id))

    files = query(
        "SELECT * FROM files WHERE folder_id=%s ORDER BY uploaded_at DESC",
        (folder_id,),
        fetchall=True
    )

    return render_template("folder.html", folder=folder, files=files)


@app.route("/folder/delete/<int:folder_id>", methods=["POST"])
@login_required
def delete_folder(folder_id):
    folder = query("""
        SELECT fo.*, c.slug category_slug
        FROM folders fo
        JOIN categories c ON c.id = fo.category_id
        WHERE fo.id = %s
    """, (folder_id,), fetchone=True)

    if not folder:
        abort(404)

    files = query(
        "SELECT stored_name FROM files WHERE folder_id=%s",
        (folder_id,),
        fetchall=True
    )

    for f in files:
        path = os.path.join(app.config["UPLOAD_FOLDER"], f["stored_name"])
        if os.path.exists(path):
            os.remove(path)

    query("DELETE FROM folders WHERE id=%s", (folder_id,), commit=True)

    flash("Folder dan semua file di dalamnya berhasil dihapus.", "success")
    return redirect(url_for("category", slug=folder["category_slug"]))


@app.route("/file/view/<int:file_id>")
@login_required
def view_file(file_id):
    f = query("SELECT * FROM files WHERE id=%s", (file_id,), fetchone=True)

    if not f:
        abort(404)

    return send_from_directory(
        app.config["UPLOAD_FOLDER"],
        f["stored_name"],
        as_attachment=False,
        download_name=f["original_name"]
    )


@app.route("/file/delete/<int:file_id>", methods=["POST"])
@login_required
def delete_file(file_id):
    f = query("SELECT * FROM files WHERE id=%s", (file_id,), fetchone=True)

    if not f:
        abort(404)

    path = os.path.join(app.config["UPLOAD_FOLDER"], f["stored_name"])

    if os.path.exists(path):
        os.remove(path)

    query("DELETE FROM files WHERE id=%s", (file_id,), commit=True)

    flash("File berhasil dihapus.", "success")
    return redirect(url_for("folder_detail", folder_id=f["folder_id"]))


init_database()


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)