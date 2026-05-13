import os
import uuid
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory, abort
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import mysql.connector
from mysql.connector import Error

app = Flask(__name__)
app.secret_key = "sipanda_secret_key_ganti_bebas_12345"

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "",
    "database": "sipanda_db",
}

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024
ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "xls", "xlsx"}

CATEGORY_SEED = [
    ("ijazah", "IJAZAH", 1), ("kk", "KK", 2), ("ktp", "KTP", 3),
    ("sk-cpns", "SK CPNS", 4), ("sk-jabatan", "SK JABATAN", 5),
    ("sk-kgb", "SK KGB ( KENAIKAN GAJI BERKALA)", 6), ("sk-pangkat", "SK PANGKAT", 7),
    ("sk-pns", "SK PNS", 8), ("skp", "SKP", 9),
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
        conn = mysql.connector.connect(host=DB_CONFIG["host"], user=DB_CONFIG["user"], password=DB_CONFIG["password"])
        cur = conn.cursor()
        cur.execute("CREATE DATABASE IF NOT EXISTS sipanda_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        conn.commit(); cur.close(); conn.close()
        with open(os.path.join(BASE_DIR, "schema.sql"), "r", encoding="utf-8") as f:
            sql = f.read().replace("CREATE DATABASE IF NOT EXISTS sipanda_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;", "").replace("USE sipanda_db;", "")
        conn = db(); cur = conn.cursor()
        for stmt in [s.strip() for s in sql.split(";") if s.strip()]:
            cur.execute(stmt)
        conn.commit(); cur.close(); conn.close()
        admin = query("SELECT id FROM users WHERE username=%s", ("admin",), fetchone=True)
        if not admin:
            query("INSERT INTO users(name, username, password, role) VALUES(%s,%s,%s,%s)",
                  ("Administrator", "admin", generate_password_hash("admin123"), "admin"), commit=True)
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

# ================= LOGIN =================

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


# ================= RESET PASSWORD =================

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

# ================= LOGOUT =================

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
    recent = query("""SELECT f.*, fo.name folder_name, c.name category_name FROM files f
                      JOIN folders fo ON fo.id=f.folder_id JOIN categories c ON c.id=fo.category_id
                      ORDER BY f.uploaded_at DESC LIMIT 8""", fetchall=True)
    return render_template("dashboard.html", stats=stats, recent=recent)

@app.route("/category/<slug>", methods=["GET", "POST"])
@login_required
def category(slug):
    cat = query("SELECT * FROM categories WHERE slug=%s", (slug,), fetchone=True)
    if not cat: abort(404)
    if request.method == "POST":
        name = request.form.get("folder_name", "").strip()
        if name:
            query("INSERT INTO folders(category_id, name, created_by) VALUES(%s,%s,%s)", (cat["id"], name, session["user_id"]), commit=True)
            flash("Folder berhasil ditambahkan.", "success")
        return redirect(url_for("category", slug=slug))
    folders = query("""SELECT fo.*, COUNT(fi.id) total_files FROM folders fo
                       LEFT JOIN files fi ON fi.folder_id=fo.id WHERE fo.category_id=%s
                       GROUP BY fo.id ORDER BY fo.created_at DESC""", (cat["id"],), fetchall=True)
    return render_template("category.html", cat=cat, folders=folders)

@app.route("/folder/<int:folder_id>", methods=["GET", "POST"])
@login_required
def folder_detail(folder_id):
    folder = query("SELECT fo.*, c.slug category_slug, c.name category_name FROM folders fo JOIN categories c ON c.id=fo.category_id WHERE fo.id=%s", (folder_id,), fetchone=True)
    if not folder: abort(404)
    if request.method == "POST":
        file = request.files.get("file")
        if file and file.filename and allowed_file(file.filename):
            original = secure_filename(file.filename)
            ext = original.rsplit(".", 1)[1].lower()
            stored = f"{uuid.uuid4().hex}.{ext}"
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], stored))
            size = os.path.getsize(os.path.join(app.config["UPLOAD_FOLDER"], stored))
            query("INSERT INTO files(folder_id, original_name, stored_name, mime_type, file_size, uploaded_by) VALUES(%s,%s,%s,%s,%s,%s)",
                  (folder_id, original, stored, file.mimetype, size, session["user_id"]), commit=True)
            flash("File berhasil diupload.", "success")
        else:
            flash("File harus Word, Excel, atau PDF.", "danger")
        return redirect(url_for("folder_detail", folder_id=folder_id))
    files = query("SELECT * FROM files WHERE folder_id=%s ORDER BY uploaded_at DESC", (folder_id,), fetchall=True)
    return render_template("folder.html", folder=folder, files=files)

@app.route("/folder/delete/<int:folder_id>", methods=["POST"])
@login_required
def delete_folder(folder_id):
    folder = query("SELECT fo.*, c.slug category_slug FROM folders fo JOIN categories c ON c.id=fo.category_id WHERE fo.id=%s", (folder_id,), fetchone=True)
    if not folder: abort(404)
    files = query("SELECT stored_name FROM files WHERE folder_id=%s", (folder_id,), fetchall=True)
    for f in files:
        path = os.path.join(app.config["UPLOAD_FOLDER"], f["stored_name"])
        if os.path.exists(path): os.remove(path)
    query("DELETE FROM folders WHERE id=%s", (folder_id,), commit=True)
    flash("Folder dan semua file di dalamnya berhasil dihapus.", "success")
    return redirect(url_for("category", slug=folder["category_slug"]))

@app.route("/file/view/<int:file_id>")
@login_required
def view_file(file_id):
    f = query("SELECT * FROM files WHERE id=%s", (file_id,), fetchone=True)
    if not f: abort(404)
    return send_from_directory(app.config["UPLOAD_FOLDER"], f["stored_name"], as_attachment=False, download_name=f["original_name"])

@app.route("/file/delete/<int:file_id>", methods=["POST"])
@login_required
def delete_file(file_id):
    f = query("SELECT * FROM files WHERE id=%s", (file_id,), fetchone=True)
    if not f: abort(404)
    path = os.path.join(app.config["UPLOAD_FOLDER"], f["stored_name"])
    if os.path.exists(path): os.remove(path)
    query("DELETE FROM files WHERE id=%s", (file_id,), commit=True)
    flash("File berhasil dihapus.", "success")
    return redirect(url_for("folder_detail", folder_id=f["folder_id"]))

if __name__ == "__main__":
    init_database()
    app.run(debug=True)
