import os
import re
import time
from functools import wraps
from datetime import datetime

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, abort, flash, send_from_directory
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy

# ----------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads", "certs")
ALLOWED_EXT = {"png", "jpg", "jpeg", "webp"}
MAX_UPLOAD_MB = 5

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-change-me")
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024

db_url = os.environ.get("DATABASE_URL", "sqlite:///" + os.path.join(BASE_DIR, "site.db"))
# Render/Heroku give postgres:// -> SQLAlchemy wants postgresql://
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# Hidden admin path — set your own secret segment via env var in production.
# e.g. ADMIN_URL_PATH=axen-ctrl-7f3q  ->  b21chat.online/axen-ctrl-7f3q/login
ADMIN_PATH = os.environ.get("ADMIN_URL_PATH", "axn-admin")


# ----------------------------------------------------------------------
# Models
# ----------------------------------------------------------------------
class AdminUser(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)


class Writeup(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(220), unique=True, nullable=False)
    event = db.Column(db.String(120))            # e.g. SekaiCTF 2026
    category = db.Column(db.String(80))           # pwn / web / crypto ...
    summary = db.Column(db.String(400))
    body_md = db.Column(db.Text, nullable=False)   # markdown/plain content
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Certification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)     # e.g. CompTIA Security+
    issuer = db.Column(db.String(200))
    image_filename = db.Column(db.String(255), nullable=False)
    link = db.Column(db.String(300))     # verification link, optional
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class SocialLink(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    label = db.Column(db.String(50), unique=True, nullable=False)  # linkedin, github...
    url = db.Column(db.String(300), nullable=False)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def slugify(text):
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text or f"writeup-{int(time.time())}"


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


def login_required(view):
    @wraps(view)
    def wrapped(*a, **kw):
        if not session.get("admin_id"):
            return redirect(url_for("admin_login"))
        return view(*a, **kw)
    return wrapped


# ----------------------------------------------------------------------
# Public routes
# ----------------------------------------------------------------------
@app.route("/")
def index():
    writeups = Writeup.query.order_by(Writeup.created_at.desc()).all()
    certs = Certification.query.order_by(Certification.created_at.desc()).all()
    socials = {s.label: s.url for s in SocialLink.query.all()}
    return render_template("index.html", writeups=writeups, certs=certs, socials=socials)


@app.route("/writeup/<slug>")
def writeup_detail(slug):
    w = Writeup.query.filter_by(slug=slug).first_or_404()
    return render_template("writeup_detail.html", w=w)


@app.route("/api/terminal", methods=["POST"])
def terminal_api():
    """Backs the front-end terminal. Returns JSON the JS can act on."""
    cmd = (request.json or {}).get("cmd", "").strip()
    parts = cmd.split()
    socials = {s.label: s.url for s in SocialLink.query.all()}

    if not parts:
        return {"type": "text", "data": ""}

    action, *rest = parts
    action = action.lower()

    if action == "help":
        return {"type": "text", "data":
                 "commands: help, open <linkedin|github|writeups|certs>, "
                 "list writeups, list certs, whoami, clear"}
    if action == "whoami":
        return {"type": "text", "data": "AXEN — cybersecurity student | pwn & web CTF player"}
    if action == "clear":
        return {"type": "clear"}
    if action == "list" and rest and rest[0] in ("writeups", "certs"):
        if rest[0] == "writeups":
            items = [w.title for w in Writeup.query.all()]
        else:
            items = [c.name for c in Certification.query.all()]
        return {"type": "text", "data": "\n".join(items) or "(empty)"}
    if action == "open" and rest:
        target = rest[0].lower()
        if target in socials:
            return {"type": "open", "url": socials[target]}
        if target in ("writeups", "certs", "certifications"):
            return {"type": "scroll", "target": "certs" if "cert" in target else "writeups"}
        return {"type": "text", "data": f"no link registered for '{target}'"}

    return {"type": "text", "data": f"command not found: {cmd}. type 'help'"}


# ----------------------------------------------------------------------
# Admin auth
# ----------------------------------------------------------------------
@app.route(f"/{ADMIN_PATH}/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        u = AdminUser.query.filter_by(username=request.form.get("username", "")).first()
        if u and u.check_password(request.form.get("password", "")):
            session["admin_id"] = u.id
            return redirect(url_for("admin_dashboard"))
        flash("Invalid credentials")
    return render_template("admin_login.html")


@app.route(f"/{ADMIN_PATH}/logout")
def admin_logout():
    session.pop("admin_id", None)
    return redirect(url_for("admin_login"))


# ----------------------------------------------------------------------
# Admin: dashboard + writeups CRUD
# ----------------------------------------------------------------------
@app.route(f"/{ADMIN_PATH}/dashboard")
@login_required
def admin_dashboard():
    writeups = Writeup.query.order_by(Writeup.created_at.desc()).all()
    certs = Certification.query.order_by(Certification.created_at.desc()).all()
    socials = SocialLink.query.all()
    return render_template("admin_dashboard.html", writeups=writeups, certs=certs, socials=socials)


@app.route(f"/{ADMIN_PATH}/writeup/new", methods=["GET", "POST"])
@login_required
def writeup_new():
    if request.method == "POST":
        title = request.form["title"].strip()
        w = Writeup(
            title=title,
            slug=slugify(title),
            event=request.form.get("event", ""),
            category=request.form.get("category", ""),
            summary=request.form.get("summary", ""),
            body_md=request.form.get("body_md", ""),
        )
        db.session.add(w)
        db.session.commit()
        return redirect(url_for("admin_dashboard"))
    return render_template("writeup_form.html", w=None)


@app.route(f"/{ADMIN_PATH}/writeup/<int:wid>/edit", methods=["GET", "POST"])
@login_required
def writeup_edit(wid):
    w = Writeup.query.get_or_404(wid)
    if request.method == "POST":
        w.title = request.form["title"].strip()
        w.event = request.form.get("event", "")
        w.category = request.form.get("category", "")
        w.summary = request.form.get("summary", "")
        w.body_md = request.form.get("body_md", "")
        db.session.commit()
        return redirect(url_for("admin_dashboard"))
    return render_template("writeup_form.html", w=w)


@app.route(f"/{ADMIN_PATH}/writeup/<int:wid>/delete", methods=["POST"])
@login_required
def writeup_delete(wid):
    w = Writeup.query.get_or_404(wid)
    db.session.delete(w)
    db.session.commit()
    return redirect(url_for("admin_dashboard"))


# ----------------------------------------------------------------------
# Admin: certifications CRUD (image upload)
# ----------------------------------------------------------------------
@app.route(f"/{ADMIN_PATH}/cert/new", methods=["GET", "POST"])
@login_required
def cert_new():
    if request.method == "POST":
        file = request.files.get("image")
        if not file or file.filename == "" or not allowed_file(file.filename):
            flash("Please upload a valid .png/.jpg/.webp file")
            return redirect(url_for("cert_new"))
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        fname = secure_filename(f"{int(time.time())}_{file.filename}")
        file.save(os.path.join(UPLOAD_DIR, fname))
        c = Certification(
            name=request.form["name"].strip(),
            issuer=request.form.get("issuer", ""),
            link=request.form.get("link", ""),
            image_filename=fname,
        )
        db.session.add(c)
        db.session.commit()
        return redirect(url_for("admin_dashboard"))
    return render_template("cert_form.html")


@app.route(f"/{ADMIN_PATH}/cert/<int:cid>/delete", methods=["POST"])
@login_required
def cert_delete(cid):
    c = Certification.query.get_or_404(cid)
    try:
        os.remove(os.path.join(UPLOAD_DIR, c.image_filename))
    except OSError:
        pass
    db.session.delete(c)
    db.session.commit()
    return redirect(url_for("admin_dashboard"))


# ----------------------------------------------------------------------
# Admin: social links (used by the terminal's `open` command)
# ----------------------------------------------------------------------
@app.route(f"/{ADMIN_PATH}/social", methods=["POST"])
@login_required
def social_save():
    label = request.form["label"].strip().lower()
    url = request.form["url"].strip()
    link = SocialLink.query.filter_by(label=label).first()
    if link:
        link.url = url
    else:
        db.session.add(SocialLink(label=label, url=url))
    db.session.commit()
    return redirect(url_for("admin_dashboard"))


# ----------------------------------------------------------------------
# CLI bootstrap: create tables + first admin user
# ----------------------------------------------------------------------
@app.cli.command("init-admin")
def init_admin():
    """flask --app app.py init-admin  (reads ADMIN_USER / ADMIN_PASS env vars)"""
    db.create_all()
    username = os.environ.get("ADMIN_USER", "axen")
    password = os.environ.get("ADMIN_PASS")
    if not password:
        print("Set ADMIN_PASS env var before running this command.")
        return
    if AdminUser.query.filter_by(username=username).first():
        print("Admin already exists.")
        return
    db.session.add(AdminUser(username=username, password_hash=generate_password_hash(password)))
    db.session.commit()
    print(f"Admin user '{username}' created.")


with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
