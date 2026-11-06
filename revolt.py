"""REVOLT OPTIMIZER – ALLES IN EINER DATEI (Optimizer + Lizenzserver + Admin-Panel).

Starten (fehlende Pakete werden automatisch installiert):

    python fivem_boost.py          -> Optimizer-App (mit Lizenzabfrage)
    python fivem_boost.py server   -> Lizenzserver + Admin-Panel (Key-Website: http://localhost:5050/admin)
    python fivem_boost.py both     -> beides auf einmal (zum Testen auf deinem PC)

Admin-Login: Benutzer "admin" + das Passwort, nach dem du beim Start gefragt wirst.
"""
import hashlib
import hmac
import json
import math
import os
import random
import re
import secrets
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import traceback
import uuid

try:
    import winreg  # nur unter Windows vorhanden
except ImportError:
    winreg = None

# ═════════════════════════ EINSTELLUNGEN ═════════════════════════
PORT = int(os.environ.get("PORT") or os.environ.get("BOOST_PORT") or 5050)
# Adresse deines Lizenzservers. Zum Testen lokal, zum Verkaufen z. B. "https://deine-domain.de"
SERVER_URL = os.environ.get"http://5.253.246.114:5050"
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")

BASE_DIR = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))
DB_PATH = os.environ.get("BOOST_DB") or os.path.join(BASE_DIR, "licenses.db")
CONF_DIR = os.path.join(os.environ.get("APPDATA", BASE_DIR), "FiveMBoost")
CONF_FILE = os.path.join(CONF_DIR, "license.json")

BG      = "#080808"   # Haupt-Hintergrund
CARD    = "#0f0f0f"   # Karten-Hintergrund
ROW     = "#131313"   # Zeilen / Einträge
LINE    = "#1e1e1e"   # Trennlinien & Rahmen
LINE2   = "#2a2a2a"   # Hellere Akzentlinie
FG      = "#f0f0f0"   # Primärer Text (leicht weicher als reines Weiß)
MUTED   = "#606060"   # Gedämpfter Text
ACCENT  = "#ffffff"   # Akzentfarbe (Buttons etc.)


def ensure(*pkgs):
    """Installiert fehlende Pakete automatisch. pkgs = (pip-Name, Modulname)."""
    if getattr(sys, "frozen", False):
        return
    import importlib.util
    missing = [p for p, mod in pkgs if importlib.util.find_spec(mod) is None]
    if missing:
        print("Installiere fehlende Pakete:", ", ".join(missing), flush=True)
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])
        except subprocess.CalledProcessError:
            raise SystemExit("Paket-Installation fehlgeschlagen. Prüfe deine Internetverbindung.")


# ═════════════════════════ LIZENZSERVER ═════════════════════════
KEY_RE = re.compile(r"^[A-Z0-9]{4}(-[A-Z0-9]{4}){3}$")
KEY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    with db() as c:
        c.execute(
            """CREATE TABLE IF NOT EXISTS licenses(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE NOT NULL,
                note TEXT DEFAULT '',
                created_at INTEGER NOT NULL,
                expires_at INTEGER,
                hwid TEXT,
                revoked INTEGER NOT NULL DEFAULT 0,
                last_seen INTEGER)"""
        )


def new_key():
    return "-".join("".join(secrets.choice(KEY_ALPHABET) for _ in range(4)) for _ in range(4))


def fmt_ts(ts):
    return time.strftime("%d.%m.%Y %H:%M", time.localtime(ts)) if ts else "–"


STYLE = """
<style>
:root{--bg:#000;--card:#0a0a0a;--row:#111;--line:#222;--fg:#fff;--muted:#8a8a8a}
*{box-sizing:border-box}
html,body{margin:0;min-height:100%}
body{background:var(--bg);color:var(--fg);font-family:Inter,"Segoe UI",system-ui,sans-serif}
canvas#snow{position:fixed;inset:0;width:100%;height:100%;pointer-events:none;z-index:0}
.wrap{position:relative;z-index:1;max-width:1040px;margin:0 auto;padding:32px 20px 60px}
h1{font-size:24px;letter-spacing:.22em;margin:0;font-weight:800}
.sub{color:var(--muted);font-size:13px;margin-top:6px}
.top{display:flex;justify-content:space-between;align-items:center;margin-bottom:26px;gap:12px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:20px}
.stat{background:rgba(10,10,10,.9);border:1px solid var(--line);border-radius:14px;padding:16px 18px}
.stat b{display:block;font-size:28px;margin-bottom:2px}
.stat span{color:var(--muted);font-size:12px}
.card{background:rgba(10,10,10,.92);border:1px solid var(--line);border-radius:16px;padding:20px;margin-bottom:20px}
.card h2{font-size:14px;margin:0 0 14px;letter-spacing:.04em}
input,select{background:#000;border:1px solid var(--line);color:var(--fg);padding:11px 13px;border-radius:10px;font-size:14px;font-family:inherit}
input:focus,select:focus{outline:none;border-color:#fff}
button{background:#fff;color:#000;border:0;padding:11px 18px;border-radius:10px;font-weight:700;cursor:pointer;font-family:inherit;transition:.15s}
button:hover{background:#d8d8d8}
button.ghost{background:transparent;color:#fff;border:1px solid var(--line)}
button.ghost:hover{border-color:#fff;background:transparent}
button.sm{padding:6px 11px;font-size:12px}
form.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.grow{flex:1;min-width:180px}
.toolbar{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px}
.tablewrap{overflow:auto}
table{width:100%;border-collapse:collapse;font-size:13px}
th{color:var(--muted);text-align:left;font-weight:500;padding:8px;border-bottom:1px solid var(--line);white-space:nowrap}
td{padding:11px 8px;border-bottom:1px solid var(--line);vertical-align:middle}
tr:hover td{background:#0d0d0d}
code{font-family:Consolas,monospace;font-size:14px;letter-spacing:.04em}
.tag{border:1px solid var(--line);border-radius:999px;padding:2px 10px;font-size:11px;color:var(--muted);white-space:nowrap}
.tag.ok{color:#fff;border-color:#fff}
.err{color:#fff;border:1px solid #fff;border-radius:10px;padding:10px;margin-bottom:12px}
.actions{display:flex;gap:6px;flex-wrap:nowrap}
.actions form{margin:0}
.newkeys{border-color:#fff}
.keyline{display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid var(--line)}
.keyline:last-of-type{border-bottom:0}
.keyline code{font-size:17px;flex:1}
.empty{color:var(--muted);text-align:center;padding:26px 0}
.toast{position:fixed;left:50%;bottom:28px;transform:translateX(-50%) translateY(20px);background:#fff;color:#000;padding:10px 18px;border-radius:10px;font-weight:700;font-size:13px;opacity:0;transition:.25s;z-index:5;pointer-events:none}
.toast.on{opacity:1;transform:translateX(-50%) translateY(0)}
@media(max-width:640px){h1{font-size:18px}}
</style>
"""

HEAD = ('<!doctype html><html lang=de><head><meta charset=utf-8>'
        '<meta name=viewport content="width=device-width,initial-scale=1"><title>TITLE</title>')

SNOW_HTML = "<canvas id=snow></canvas>"

SNOW_JS = """
(function(){
if(matchMedia('(prefers-reduced-motion: reduce)').matches)return;
var c=document.getElementById('snow'),x=c.getContext('2d'),W,H,f=[];
function rs(){W=c.width=innerWidth;H=c.height=innerHeight}
rs();addEventListener('resize',rs);
for(var i=0;i<110;i++)f.push({x:Math.random()*W,y:Math.random()*H,r:Math.random()*2.2+.6,v:Math.random()*.8+.3,p:Math.random()*6.28,s:Math.random()*.6+.2});
function t(){x.clearRect(0,0,W,H);
for(var i=0;i<f.length;i++){var o=f[i];o.y+=o.v;o.p+=.01;o.x+=Math.sin(o.p)*o.s;
if(o.y>H+5){o.y=-5;o.x=Math.random()*W}
x.globalAlpha=.25+o.r/3.2*.6;x.fillStyle='#fff';x.beginPath();x.arc(o.x,o.y,o.r,0,6.283);x.fill()}
requestAnimationFrame(t)}
t()})();
"""

ADMIN_JS = """
function toast(m){var t=document.getElementById('toast');t.textContent=m;t.className='toast on';
clearTimeout(window._t);window._t=setTimeout(function(){t.className='toast'},1600)}
function copyText(s){
function fb(){var a=document.createElement('textarea');a.value=s;document.body.appendChild(a);a.select();
try{document.execCommand('copy');toast('Kopiert')}catch(e){toast('Kopieren nicht möglich')}a.remove()}
if(navigator.clipboard&&window.isSecureContext){navigator.clipboard.writeText(s).then(function(){toast('Kopiert')},fb)}else{fb()}}
function filt(){
var q=document.getElementById('q').value.toLowerCase().trim(),st=document.getElementById('st').value,n=0;
document.querySelectorAll('#tb tr[data-s]').forEach(function(r){
var ok=(!q||r.dataset.q.indexOf(q)>-1)&&(!st||r.dataset.s===st);r.style.display=ok?'':'none';if(ok)n++});
var e=document.getElementById('none');if(e)e.style.display=n?'none':'block'}
"""

LOGIN_HTML = (
    HEAD.replace("TITLE", "Admin Login") + STYLE + "</head><body>" + SNOW_HTML
    + """
<div class=wrap style="max-width:400px;padding-top:14vh">
<h1>REVOLT OPTIMIZER</h1><div class=sub style="margin-bottom:22px">Admin-Login</div>
{% if error %}<div class=err>{{ error }}</div>{% endif %}
<form method=post class=card style="display:grid;gap:12px">
<input name=user placeholder=Benutzer autofocus>
<input name=password type=password placeholder=Passwort>
<button>Anmelden</button></form></div>
<script>""" + SNOW_JS + "</script></body></html>"
)

ADMIN_HTML = (
    HEAD.replace("TITLE", "Key-Verwaltung") + STYLE + "</head><body>" + SNOW_HTML
    + """
<div class=wrap>
<div class=top><div><h1>REVOLT OPTIMIZER</h1><div class=sub>Key-Verwaltung</div></div>
<a href=/admin/logout><button class=ghost>Logout</button></a></div>

<div class=stats>
<div class=stat><b>{{ stats.total }}</b><span>Keys gesamt</span></div>
<div class=stat><b>{{ stats.active }}</b><span>Aktiv</span></div>
<div class=stat><b>{{ stats.expired }}</b><span>Abgelaufen</span></div>
<div class=stat><b>{{ stats.revoked }}</b><span>Gesperrt</span></div>
<div class=stat><b>{{ stats.bound }}</b><span>PCs verbunden</span></div>
</div>

<div class=card><h2>NEUE KEYS ERSTELLEN</h2>
<form class=row method=post action=/admin/create>
<input type=hidden name=csrf value="{{ csrf }}">
<input class=grow name=note placeholder="Notiz / Kunde (optional)" maxlength=100>
<select name=days title="Gültigkeit">
<option value=1>1 Tag</option><option value=7>7 Tage</option><option value=30 selected>30 Tage</option>
<option value=90>90 Tage</option><option value=365>1 Jahr</option><option value=0>Lifetime</option></select>
<input name=count type=number min=1 max=50 value=1 style="width:90px" title="Anzahl">
<button>Key erstellen</button></form></div>

{% if new_keys %}<div class="card newkeys"><h2>✔ {{ new_keys|length }} NEUE{{ 'R KEY' if new_keys|length == 1 else ' KEYS' }} ERSTELLT</h2>
{% for k in new_keys %}<div class=keyline><code>{{ k }}</code><button class="ghost sm" onclick="copyText('{{ k }}')">Kopieren</button></div>{% endfor %}
<div style="margin-top:14px"><button onclick='copyText({{ new_keys|join("\\n")|tojson }})'>Alle kopieren</button></div></div>{% endif %}

<div class=card><h2>ALLE KEYS</h2>
<div class=toolbar>
<input id=q class=grow placeholder="Suchen (Key oder Notiz) …" oninput="filt()">
<select id=st onchange="filt()"><option value="">Alle Status</option><option value=aktiv>Aktiv</option>
<option value=abgelaufen>Abgelaufen</option><option value=gesperrt>Gesperrt</option></select></div>
<div class=tablewrap><table>
<tr><th>Key</th><th>Notiz</th><th>Status</th><th>Läuft ab</th><th>Zuletzt aktiv</th><th>PC</th><th></th></tr>
<tbody id=tb>
{% for r in rows %}<tr data-s="{{ r.status }}" data-q="{{ (r.key ~ ' ' ~ r.note)|lower }}">
<td><code>{{ r.key }}</code></td><td>{{ r.note }}</td>
<td>{% if r.status == 'aktiv' %}<span class="tag ok">aktiv</span>{% else %}<span class=tag>{{ r.status }}</span>{% endif %}</td>
<td>{{ r.exp }}</td><td>{{ r.seen }}</td><td>{{ 'gebunden' if r.hwid else 'frei' }}</td>
<td><div class=actions>
<button class="ghost sm" onclick="copyText('{{ r.key }}')">Kopieren</button>
<form method=post action="/admin/{{ r.id }}/toggle"><input type=hidden name=csrf value="{{ csrf }}"><button class="ghost sm">{{ 'Entsperren' if r.revoked else 'Sperren' }}</button></form>
<form method=post action="/admin/{{ r.id }}/reset"><input type=hidden name=csrf value="{{ csrf }}"><button class="ghost sm">PC lösen</button></form>
<form method=post action="/admin/{{ r.id }}/delete" onsubmit="return confirm('Key wirklich löschen?')"><input type=hidden name=csrf value="{{ csrf }}"><button class="ghost sm">Löschen</button></form>
</div></td></tr>
{% endfor %}</tbody></table></div>
{% if not rows %}<div class=empty>Noch keine Keys – erstelle oben deinen ersten.</div>
{% else %}<div id=none class=empty style="display:none">Keine Treffer.</div>{% endif %}
</div></div>
<div id=toast class=toast></div>
<script>""" + SNOW_JS + ADMIN_JS + "</script></body></html>"
)


def create_app(admin_password):
    from functools import wraps

    from flask import (Flask, abort, jsonify, redirect, render_template_string,
                       request, session)
    from werkzeug.exceptions import HTTPException

    init_db()  # Tabelle wird bei JEDEM Start angelegt, falls sie fehlt
    app = Flask(__name__)
    app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Strict")
    hits = {}

    def rate_limited(name):
        now = time.time()
        lst = [t for t in hits.get(name, []) if now - t < 60]
        lst.append(now)
        hits[name] = lst
        return len(lst) > 20

    # ───── CORS Support für externe / lokale Websites ─────
    @app.after_request
    def add_cors(resp):
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
        return resp

    @app.route("/api/<path:path>", methods=["OPTIONS"])
    def api_cors_options(path):
        return ("", 204)

    # ───── Token Generierung & Validierung ─────
    def make_token():
        exp = int(time.time()) + 7 * 86400  # 7 Tage gültig
        raw = f"{ADMIN_USER}:{exp}"
        sig = hmac.new(app.secret_key.encode(), raw.encode(), hashlib.sha256).hexdigest()
        return f"{raw}:{sig}"

    def verify_token(tok):
        if not tok:
            return False
        parts = tok.split(":")
        if len(parts) != 3:
            return False
        user, exp_str, sig = parts
        try:
            exp = int(exp_str)
        except ValueError:
            return False
        if exp < time.time():
            return False
        if not hmac.compare_digest(user, ADMIN_USER):
            return False
        expected_sig = hmac.new(app.secret_key.encode(), f"{user}:{exp}".encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, expected_sig)

    @app.errorhandler(Exception)
    def on_error(e):
        if isinstance(e, HTTPException):
            return e
        traceback.print_exc()  # Details erscheinen im Server-Fenster
        detail = f"{type(e).__name__}: {e}" if session.get("admin") else "Interner Fehler."
        return f"Fehler: {detail}", 500

    def admin_required(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if not session.get("admin"):
                return redirect("/admin/login")
            if request.method == "POST":
                if not hmac.compare_digest(request.form.get("csrf", ""), session.get("csrf", "")):
                    abort(400)
            return fn(*a, **kw)

        return wrapper

    def api_admin_required(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            auth = request.headers.get("Authorization", "")
            tok = auth.replace("Bearer ", "").strip() if auth.startswith("Bearer ") else None
            if not tok and session.get("admin"):
                return fn(*a, **kw)
            if not tok or not verify_token(tok):
                return jsonify(success=False, error="Nicht autorisiert oder Sitzung abgelaufen."), 401
            return fn(*a, **kw)

        return wrapper

    # ───── Client-API ─────
    @app.get("/api/ping")
    def api_ping():
        return jsonify(status="ok", name="REVOLT OPTIMIZER Server", version="2.0")

    @app.post("/api/validate")
    def validate():
        if rate_limited("api:" + str(request.remote_addr)):
            return jsonify(valid=False, error="Zu viele Anfragen, bitte warten."), 429
        data = request.get_json(silent=True) or {}
        key = str(data.get("key", "")).strip().upper()
        hwid = str(data.get("hwid", ""))[:128]
        if not KEY_RE.match(key) or not hwid:
            return jsonify(valid=False, error="Ungültiger Lizenzkey."), 400
        now = int(time.time())
        with db() as c:
            row = c.execute("SELECT * FROM licenses WHERE key=?", (key,)).fetchone()
            if not row:
                return jsonify(valid=False, error="Lizenzkey nicht gefunden."), 403
            if row["revoked"]:
                return jsonify(valid=False, error="Dieser Key wurde gesperrt."), 403
            if row["expires_at"] and row["expires_at"] < now:
                return jsonify(valid=False, error="Dieser Key ist abgelaufen."), 403
            if row["hwid"] and row["hwid"] != hwid:
                return jsonify(valid=False, error="Key ist an einen anderen PC gebunden."), 403
            c.execute("UPDATE licenses SET hwid=COALESCE(hwid, ?), last_seen=? WHERE id=?",
                      (hwid, now, row["id"]))
        return jsonify(valid=True, expires_at=row["expires_at"])

    # ───── REST-API für Web-Adminpanel (lizenzverwaltung.html) ─────
    @app.post("/api/admin/login")
    def api_admin_login():
        if rate_limited("login:" + str(request.remote_addr)):
            return jsonify(success=False, error="Zu viele Versuche, bitte kurz warten."), 429
        data = request.get_json(silent=True) or {}
        u = str(data.get("user", "")).strip()
        p = str(data.get("password", "")).strip()
        u_ok = hmac.compare_digest(u, ADMIN_USER)
        p_ok = hmac.compare_digest(p, admin_password)
        if u_ok and p_ok:
            tok = make_token()
            session.clear()
            session["admin"] = True
            session["csrf"] = secrets.token_hex(16)
            return jsonify(success=True, token=tok, user=ADMIN_USER, expires_in=7 * 86400)
        return jsonify(success=False, error="Falscher Benutzername oder Passwort."), 401

    @app.get("/api/admin/licenses")
    @api_admin_required
    def api_admin_licenses_list():
        now = int(time.time())
        today_start = now - 86400
        with db() as c:
            raw = c.execute("SELECT * FROM licenses ORDER BY id DESC").fetchall()
        rows = []
        stats = {"total": len(raw), "active": 0, "expired": 0, "revoked": 0, "bound": 0, "today_active": 0}
        for r in raw:
            expired = bool(r["expires_at"] and r["expires_at"] < now)
            if r["revoked"]:
                status = "gesperrt"
                stats["revoked"] += 1
            elif expired:
                status = "abgelaufen"
                stats["expired"] += 1
            else:
                status = "aktiv"
                stats["active"] += 1
            if r["hwid"]:
                stats["bound"] += 1
            if r["last_seen"] and r["last_seen"] >= today_start:
                stats["today_active"] += 1
            rows.append({
                "id": r["id"],
                "key": r["key"],
                "note": r["note"] or "",
                "created_at": r["created_at"],
                "expires_at": r["expires_at"],
                "hwid": r["hwid"],
                "bound": bool(r["hwid"]),
                "revoked": bool(r["revoked"]),
                "status": status,
                "last_seen": r["last_seen"]
            })
        return jsonify(success=True, licenses=rows, stats=stats)

    @app.post("/api/admin/licenses")
    @api_admin_required
    def api_admin_licenses_create():
        data = request.get_json(silent=True) or {}
        note = str(data.get("note", "")).strip()[:100]
        days = max(0, int(data.get("days", 0) or 0))
        count = min(100, max(1, int(data.get("count", 1) or 1)))
        custom_key = str(data.get("custom_key", "")).strip().upper()
        now = int(time.time())
        exp = now + days * 86400 if days else None
        created = []
        with db() as c:
            if custom_key:
                if not KEY_RE.match(custom_key):
                    return jsonify(success=False, error="Wunsch-Key muss das Format XXXX-XXXX-XXXX-XXXX haben."), 400
                exists = c.execute("SELECT id FROM licenses WHERE key=?", (custom_key,)).fetchone()
                if exists:
                    return jsonify(success=False, error="Dieser Key existiert bereits."), 400
                c.execute("INSERT INTO licenses(key, note, created_at, expires_at) VALUES(?,?,?,?)",
                          (custom_key, note, now, exp))
                created.append(custom_key)
            else:
                for _ in range(count):
                    k = new_key()
                    while c.execute("SELECT id FROM licenses WHERE key=?", (k,)).fetchone():
                        k = new_key()
                    c.execute("INSERT INTO licenses(key, note, created_at, expires_at) VALUES(?,?,?,?)",
                              (k, note, now, exp))
                    created.append(k)
        return jsonify(success=True, keys=created, count=len(created), days=days, note=note)

    @app.route("/api/admin/licenses/<int:lid>", methods=["PUT", "PATCH"])
    @api_admin_required
    def api_admin_license_update(lid):
        data = request.get_json(silent=True) or {}
        with db() as c:
            row = c.execute("SELECT * FROM licenses WHERE id=?", (lid,)).fetchone()
            if not row:
                return jsonify(success=False, error="Lizenz nicht gefunden."), 404
            note = str(data.get("note", row["note"])).strip()[:100] if "note" in data else row["note"]
            revoked = int(bool(data.get("revoked", row["revoked"]))) if "revoked" in data else row["revoked"]
            hwid = row["hwid"]
            if data.get("reset_hwid"):
                hwid = None
            elif "hwid" in data:
                hwid = str(data["hwid"]).strip() or None
            expires_at = row["expires_at"]
            if "expires_at" in data:
                expires_at = data["expires_at"]
                if expires_at is not None:
                    expires_at = int(expires_at)
            c.execute("UPDATE licenses SET note=?, revoked=?, hwid=?, expires_at=? WHERE id=?",
                       (note, revoked, hwid, expires_at, lid))
        return jsonify(success=True)

    @app.post("/api/admin/licenses/<int:lid>/toggle")
    @api_admin_required
    def api_admin_license_toggle(lid):
        with db() as c:
            row = c.execute("SELECT revoked FROM licenses WHERE id=?", (lid,)).fetchone()
            if not row:
                return jsonify(success=False, error="Lizenz nicht gefunden."), 404
            new_revoked = 1 - row["revoked"]
            c.execute("UPDATE licenses SET revoked=? WHERE id=?", (new_revoked, lid))
        return jsonify(success=True, revoked=bool(new_revoked))

    @app.post("/api/admin/licenses/<int:lid>/reset")
    @api_admin_required
    def api_admin_license_reset(lid):
        with db() as c:
            c.execute("UPDATE licenses SET hwid=NULL WHERE id=?", (lid,))
        return jsonify(success=True)

    @app.post("/api/admin/licenses/<int:lid>/extend")
    @api_admin_required
    def api_admin_license_extend(lid):
        data = request.get_json(silent=True) or {}
        days = int(data.get("days", 30))
        now = int(time.time())
        with db() as c:
            row = c.execute("SELECT expires_at FROM licenses WHERE id=?", (lid,)).fetchone()
            if not row:
                return jsonify(success=False, error="Lizenz nicht gefunden."), 404
            if days == 0:
                new_exp = None
            else:
                cur_exp = row["expires_at"]
                base_time = cur_exp if (cur_exp and cur_exp > now) else now
                new_exp = base_time + days * 86400
            c.execute("UPDATE licenses SET expires_at=? WHERE id=?", (new_exp, lid))
        return jsonify(success=True, expires_at=new_exp)

    @app.delete("/api/admin/licenses/<int:lid>")
    @api_admin_required
    def api_admin_license_delete(lid):
        with db() as c:
            c.execute("DELETE FROM licenses WHERE id=?", (lid,))
        return jsonify(success=True)

    # ───── Klassischer Admin-Zugang (HTML) ─────
    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        error = None
        if request.method == "POST":
            if rate_limited("login:" + str(request.remote_addr)):
                error = "Zu viele Versuche, bitte warten."
            else:
                u_ok = hmac.compare_digest(request.form.get("user", ""), ADMIN_USER)
                p_ok = hmac.compare_digest(request.form.get("password", ""), admin_password)
                if u_ok and p_ok:
                    session.clear()
                    session["admin"] = True
                    session["csrf"] = secrets.token_hex(16)
                    return redirect("/admin")
                error = "Falsche Zugangsdaten."
        return render_template_string(LOGIN_HTML, error=error)

    @app.route("/admin/logout")
    def admin_logout():
        session.clear()
        return redirect("/admin/login")

    @app.route("/admin")
    def admin_home():
        # Falls lizenzverwaltung.html im selben Verzeichnis liegt, liefere diese moderne Website aus
        html_path = os.path.join(BASE_DIR, "lizenzverwaltung.html")
        if os.path.isfile(html_path):
            with open(html_path, "r", encoding="utf-8") as f:
                return f.read()

        if not session.get("admin"):
            return redirect("/admin/login")

        now = int(time.time())
        with db() as c:
            raw = c.execute("SELECT * FROM licenses ORDER BY id DESC").fetchall()
        rows = []
        stats = {"total": len(raw), "active": 0, "expired": 0, "revoked": 0, "bound": 0}
        for r in raw:
            expired = bool(r["expires_at"] and r["expires_at"] < now)
            if r["revoked"]:
                status = "gesperrt"
                stats["revoked"] += 1
            elif expired:
                status = "abgelaufen"
                stats["expired"] += 1
            else:
                status = "aktiv"
                stats["active"] += 1
            if r["hwid"]:
                stats["bound"] += 1
            rows.append({**dict(r), "status": status,
                         "exp": fmt_ts(r["expires_at"]) if r["expires_at"] else "unbegrenzt",
                         "seen": fmt_ts(r["last_seen"])})
        new_keys = session.pop("new_keys", [])
        return render_template_string(ADMIN_HTML, rows=rows, stats=stats, new_keys=new_keys,
                                      csrf=session["csrf"])

    @app.post("/admin/create")
    @admin_required
    def admin_create():
        note = request.form.get("note", "").strip()[:100]
        days = max(0, int(request.form.get("days", 0) or 0))
        count = min(50, max(1, int(request.form.get("count", 1) or 1)))
        now = int(time.time())
        exp = now + days * 86400 if days else None
        created = []
        with db() as c:
            for _ in range(count):
                k = new_key()
                c.execute("INSERT INTO licenses(key, note, created_at, expires_at) VALUES(?,?,?,?)",
                          (k, note, now, exp))
                created.append(k)
        session["new_keys"] = created
        return redirect("/admin")

    @app.post("/admin/<int:lid>/toggle")
    @admin_required
    def admin_toggle(lid):
        with db() as c:
            c.execute("UPDATE licenses SET revoked = 1 - revoked WHERE id=?", (lid,))
        return redirect("/admin")

    @app.post("/admin/<int:lid>/reset")
    @admin_required
    def admin_reset(lid):
        with db() as c:
            c.execute("UPDATE licenses SET hwid=NULL WHERE id=?", (lid,))
        return redirect("/admin")

    @app.post("/admin/<int:lid>/delete")
    @admin_required
    def admin_delete(lid):
        with db() as c:
            c.execute("DELETE FROM licenses WHERE id=?", (lid,))
        return redirect("/admin")

    @app.route("/")
    def index():
        return redirect("/admin")

    return app


def ask_password():
    pw = os.environ.get("ADMIN_PASSWORD", "")
    if pw:
        return pw
    # Auf Cloud-Servern (wie Render) gibt es keine Tastatureingabe
    if not sys.stdin or not sys.stdin.isatty():
        print("Hinweis: Kein ADMIN_PASSWORD gesetzt. Standard-Passwort 'admin123' aktiv.", flush=True)
        return "admin123"
    while not pw:
        pw = input("Admin-Passwort festlegen (damit loggst du dich unter /admin ein): ").strip()
    return pw


def run_server(password):
    ensure(("flask", "flask"))
    app = create_app(password)
    print(f"\n✔ Server läuft.  Admin-Bereich: http://localhost:{PORT}/admin")
    print(f"  Benutzer: {ADMIN_USER}   Passwort: (das eben eingegebene)")
    print("  Dieses Fenster muss offen bleiben. Beenden mit STRG+C.\n", flush=True)
    app.run(host="0.0.0.0", port=PORT, threaded=True)


# ═════════════════════════ OPTIMIERUNGEN (Windows) ═════════════════════════
NO_WINDOW = 0x08000000


def _run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, creationflags=NO_WINDOW)
    return r.returncode == 0


def _size(path):
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def _clear_dir(path):
    if not os.path.isdir(path):
        return 0
    freed = 0
    for name in os.listdir(path):
        p = os.path.join(path, name)
        try:
            if os.path.isdir(p) and not os.path.islink(p):
                s = _size(p)
                shutil.rmtree(p, ignore_errors=True)
                freed += s if not os.path.exists(p) else 0
            else:
                s = os.path.getsize(p)
                os.remove(p)
                freed += s
        except OSError:
            pass
    return freed


def _mb(b):
    return f"{b / 1024 / 1024:.1f} MB"


def _set_reg(path, name, value, kind=None):
    kind = winreg.REG_DWORD if kind is None else kind
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, name, 0, kind, value)


def fivem_dir():
    return os.path.join(os.environ.get("LOCALAPPDATA", ""), "FiveM")


def clear_fivem_cache():
    base = os.path.join(fivem_dir(), "FiveM.app", "data")
    if not os.path.isdir(base):
        return "FiveM-Ordner nicht gefunden – übersprungen."
    freed = sum(_clear_dir(os.path.join(base, s))
                for s in ("cache", "server-cache", "server-cache-priv", "nui-storage"))
    return f"FiveM-Cache geleert ({_mb(freed)} frei)."


def clear_temp():
    freed = 0
    for p in (os.environ.get("TEMP"), os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Temp")):
        if p:
            freed += _clear_dir(p)
    return f"Temporäre Dateien gelöscht ({_mb(freed)} frei)."


def clear_shader_cache():
    local = os.environ.get("LOCALAPPDATA", "")
    freed = sum(_clear_dir(os.path.join(local, s))
                for s in (r"NVIDIA\DXCache", r"NVIDIA\GLCache", r"AMD\DxCache", r"D3DSCache"))
    return f"Shader-Cache geleert ({_mb(freed)} frei)."


def flush_dns():
    return "DNS-Cache geleert." if _run(["ipconfig", "/flushdns"]) else "DNS-Cache konnte nicht geleert werden."


def high_performance_plan():
    ok = _run(["powercfg", "/setactive", "SCHEME_MIN"])
    return "Energiesparplan: Höchstleistung aktiv." if ok else "Energiesparplan konnte nicht gesetzt werden."


def game_mode_on():
    _set_reg(r"Software\Microsoft\GameBar", "AutoGameModeEnabled", 1)
    _set_reg(r"Software\Microsoft\GameBar", "AllowAutoGameMode", 1)
    return "Windows-Spielmodus aktiviert."


def disable_game_dvr():
    _set_reg(r"System\GameConfigStore", "GameDVR_Enabled", 0)
    _set_reg(r"Software\Microsoft\Windows\CurrentVersion\GameDVR", "AppCaptureEnabled", 0)
    return "Game DVR / Hintergrundaufnahme deaktiviert."


def gpu_high_performance():
    exe = os.path.join(fivem_dir(), "FiveM.exe")
    if not os.path.isfile(exe):
        return "FiveM.exe nicht gefunden – GPU-Einstellung übersprungen."
    _set_reg(r"Software\Microsoft\DirectX\UserGpuPreferences", exe, "GpuPreference=2;", winreg.REG_SZ)
    return "FiveM nutzt jetzt die leistungsstarke GPU."


def boost_priority():
    import psutil
    hit = 0
    for p in psutil.process_iter(["name"]):
        n = (p.info["name"] or "").lower()
        if n.startswith("fivem_") and "gtaprocess" in n:
            try:
                p.nice(psutil.HIGH_PRIORITY_CLASS)
                hit += 1
            except psutil.Error:
                pass
    return "FiveM-Prozess auf hohe Priorität gesetzt." if hit else "FiveM läuft nicht – bitte nach dem Start erneut ausführen."


def clean_system_ram():
    import ctypes
    import psutil
    before = psutil.virtual_memory().used
    kernel32 = ctypes.windll.kernel32
    PROCESS_ALL_ACCESS = 0x1F0FFF
    count = 0
    for p in psutil.process_iter(["pid"]):
        try:
            pid = p.info["pid"]
            if pid <= 4:
                continue
            h = kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)
            if h:
                kernel32.SetProcessWorkingSetSize(h, -1, -1)
                kernel32.CloseHandle(h)
                count += 1
        except Exception:
            pass
    after = psutil.virtual_memory().used
    freed = max(0, before - after)
    return f"RAM bereinigt ({_mb(freed)} freigegeben, {count} Prozesse optimiert)."


def fix_fivem_texture_loss():
    base = os.path.join(fivem_dir(), "FiveM.app")
    ini_path = os.path.join(base, "CitizenFX.ini")
    if not os.path.isdir(base):
        return "FiveM-Ordner (%LOCALAPPDATA%\\FiveM) nicht gefunden – übersprungen."
    try:
        lines = []
        if os.path.isfile(ini_path):
            with open(ini_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
        settings = {
            "DisableNVSP": "1",
            "disableTelemetry": "1",
            "streaming_memoryBudget": "4000",
            "DisableAudioStreamerCrashReporting": "1",
        }
        has_game = False
        new_lines = []
        for line in lines:
            sline = line.strip()
            if sline.lower() == "[game]":
                has_game = True
                new_lines.append(line)
                continue
            k = sline.split("=")[0].strip() if "=" in sline else ""
            if k in settings:
                continue
            new_lines.append(line)
        pos = [i for i, l in enumerate(new_lines) if l.strip().lower() == "[game]"]
        insert_pos = (pos[0] + 1) if pos else 1
        if not has_game:
            new_lines.insert(0, "[Game]\n")
        for k, v in settings.items():
            new_lines.insert(insert_pos, f"{k}={v}\n")
        with open(ini_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
        return "Texture Loss Fix aktiv (Streaming-Budget 4000 MB, Telemetrie aus)."
    except Exception as e:
        return f"CitizenFX.ini Fehler: {e}"


def clear_fivem_dumps():
    base = os.path.join(fivem_dir(), "FiveM.app")
    if not os.path.isdir(base):
        return "FiveM-Ordner nicht gefunden – übersprungen."
    freed = 0
    for folder in ("crashes", "logs"):
        p = os.path.join(base, folder)
        if os.path.isdir(p):
            freed += _clear_dir(p)
    return f"Crash-Dumps & Logs gelöscht ({_mb(freed)} frei)."


def optimize_network():
    try:
        _set_reg(r"Software\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile", "NetworkThrottlingIndex", 0xFFFFFFFF)
        _set_reg(r"Software\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile", "SystemResponsiveness", 0)
        _set_reg(r"Software\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Games", "GPU Priority", 8)
        _set_reg(r"Software\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Games", "Priority", 6)
        _set_reg(r"Software\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Games", "Scheduling Category", "High", winreg.REG_SZ)
    except Exception:
        pass
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces", 0, winreg.KEY_READ) as root:
            count = winreg.QueryInfoKey(root)[0]
            for i in range(count):
                sub = winreg.EnumKey(root, i)
                try:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, rf"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces\{sub}", 0, winreg.KEY_SET_VALUE) as iface:
                        winreg.SetValueEx(iface, "TcpAckFrequency", 0, winreg.REG_DWORD, 1)
                        winreg.SetValueEx(iface, "TCPNoDelay", 0, winreg.REG_DWORD, 1)
                except Exception:
                    pass
    except Exception:
        pass
    return "Netzwerk & Ping optimiert (Nagle aus, Gaming-Traffic priorisiert)."


def optimize_input_lag():
    _set_reg(r"Control Panel\Mouse", "MouseSpeed", "0", winreg.REG_SZ)
    _set_reg(r"Control Panel\Mouse", "MouseThreshold1", "0", winreg.REG_SZ)
    _set_reg(r"Control Panel\Mouse", "MouseThreshold2", "0", winreg.REG_SZ)
    _set_reg(r"Control Panel\Desktop", "MenuShowDelay", "0", winreg.REG_SZ)
    return "Input-Lag reduziert (1:1 Raw Mouse Aim, Menü-Verzögerung 0ms)."


def unpark_cpu_cores():
    ok1 = _run(["powercfg", "-setacvalueindex", "SCHEME_CURRENT", "SUB_PROCESSOR", "CPMINCORES", "100"])
    ok2 = _run(["powercfg", "-setactive", "SCHEME_CURRENT"])
    return "CPU Core Unparking aktiv (Alle Kerne auf 100% ohne Drosselung)." if (ok1 or ok2) else "Core Unparking konnte nicht angewendet werden."


def optimize_gta_settings():
    up = os.environ.get("USERPROFILE", "")
    paths = [
        os.path.join(up, "Documents", "Rockstar Games", "GTA V", "settings.xml"),
        os.path.join(up, "OneDrive", "Dokumente", "Rockstar Games", "GTA V", "settings.xml"),
        os.path.join(up, "OneDrive", "Documents", "Rockstar Games", "GTA V", "settings.xml"),
    ]
    target = next((p for p in paths if os.path.isfile(p)), None)
    if not target:
        return "GTA V settings.xml nicht gefunden – übersprungen."
    try:
        with open(target, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        bak = target + ".backup"
        if not os.path.exists(bak):
            with open(bak, "w", encoding="utf-8") as f:
                f.write(content)
        content = re.sub(r'<ShadowQuality value="[1-9]"', '<ShadowQuality value="0"', content)
        content = re.sub(r'<GrassQuality value="[1-9]"', '<GrassQuality value="0"', content)
        content = re.sub(r'<ReflectionQuality value="[1-9]"', '<ReflectionQuality value="0"', content)
        content = re.sub(r'<WaterQuality value="[1-9]"', '<WaterQuality value="0"', content)
        content = re.sub(r'<ParticleQuality value="[1-9]"', '<ParticleQuality value="0"', content)
        content = re.sub(r'<PostFX value="[1-9]"', '<PostFX value="0"', content)
        with open(target, "w", encoding="utf-8") as f:
            f.write(content)
        return "GTA V Settings optimiert (Gras, Schatten & Partikel auf Normal + Backup erstellt)."
    except Exception as e:
        return f"GTA V settings.xml Fehler: {e}"


TWEAKS = [
    ("fivem_cache", "FiveM-Cache leeren", "Löscht cache, server-cache und nui-storage – behebt Ruckler & Textur-Bugs.", clear_fivem_cache),
    ("texture_loss", "FiveM Texture Loss Fix", "Erhöht Streaming-Budget auf 4000 MB – verhindert unsichtbare Straßen & Gebäude.", fix_fivem_texture_loss),
    ("ram_cleaner", "RAM-Cleaner (Live Arbeitsspeicher)", "Bereinigt Working-Sets laufender Prozesse & gibt ungenutzten RAM frei.", clean_system_ram),
    ("network", "Ping & Hitreg Optimizer", "Deaktiviert Nagle-Algorithmus (TCPNoDelay) & priorisiert Game-Traffic.", optimize_network),
    ("input_lag", "1:1 Raw Mouse Aim & Input-Lag", "Entfernt Windows-Mausbeschleunigung & setzt Menü-Verzögerung auf 0 ms.", optimize_input_lag),
    ("cpu_unpark", "CPU Core Unparking", "Verhindert, dass Windows CPU-Kerne in den Schlafmodus versetzt (keine Micro-Stutters).", unpark_cpu_cores),
    ("gta_settings", "GTA V Ultra FPS Config", "Optimiert Schatten-, Gras- und Partikelqualität (inkl. automatischem Backup).", optimize_gta_settings),
    ("crash_dumps", "FiveM Crash-Dumps & Logs leeren", "Entfernt alte .dmp Crash-Dateien und riesige Log-Archive.", clear_fivem_dumps),
    ("temp", "Temp-Dateien löschen", "Entfernt temporäre Windows- und Benutzerdateien.", clear_temp),
    ("shader", "Shader-Cache leeren", "Setzt NVIDIA/AMD/DirectX-Shader-Caches zurück.", clear_shader_cache),
    ("dns", "DNS-Cache leeren", "Hilft bei Verbindungsproblemen zu FiveM-Servern.", flush_dns),
    ("power", "Höchstleistung-Energieplan", "Verhindert CPU-Drosselung beim Spielen.", high_performance_plan),
    ("gamemode", "Spielmodus aktivieren", "Priorisiert Spiele im Windows-Scheduler.", game_mode_on),
    ("dvr", "Game DVR deaktivieren", "Stoppt Hintergrundaufnahmen, die FPS kosten.", disable_game_dvr),
    ("gpu", "GPU-Priorität für FiveM", "Erzwingt die dedizierte Grafikkarte.", gpu_high_performance),
    ("priority", "FiveM-Priorität erhöhen", "Setzt den laufenden FiveM-Prozess auf „Hoch“.", boost_priority),
]


# ═════════════════════════ LIZENZ (Client) ═════════════════════════
def get_hwid():
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography", 0,
                            winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as k:
            guid = winreg.QueryValueEx(k, "MachineGuid")[0]
    except (OSError, AttributeError):
        guid = str(uuid.getnode())
    return hashlib.sha256(guid.encode()).hexdigest()[:32]


def check_license(key):
    """Gibt (ok, fehlertext, ablaufzeit) zurück."""
    import requests
    try:
        r = requests.post(f"{SERVER_URL}/api/validate", json={"key": key, "hwid": get_hwid()}, timeout=8)
        data = r.json()
    except requests.RequestException:
        return False, "Lizenzserver nicht erreichbar.", None
    except ValueError:
        return False, "Ungültige Serverantwort.", None
    if data.get("valid"):
        return True, "", data.get("expires_at")
    return False, data.get("error", "Lizenz ungültig."), None


def load_key():
    try:
        with open(CONF_FILE, encoding="utf-8") as f:
            return json.load(f).get("key", "")
    except (OSError, ValueError):
        return ""


def save_key(key):
    os.makedirs(CONF_DIR, exist_ok=True)
    with open(CONF_FILE, "w", encoding="utf-8") as f:
        json.dump({"key": key}, f)


# ═════════════════════════ EINSTELLUNGEN (Client) ═════════════════════════
SETTINGS_FILE = os.path.join(CONF_DIR, "settings.json")


def load_settings():
    default = {
        "fx_mode": "snow",  # snow, matrix, stars, neon, off
        "play_sound": True,
    }
    try:
        if os.path.isfile(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                default.update(data)
    except Exception:
        pass
    return default


def save_settings(cfg):
    try:
        os.makedirs(CONF_DIR, exist_ok=True)
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass


# ═════════════════════════ HINTERGRUND-EFFEKTE ═════════════════════════
class BackgroundFX:
    """Animierte Hintergrund-Effekte (Schnee, Matrix, Sterne, Neon) auf einem tk.Canvas."""

    def __init__(self, canvas, mode="snow"):
        self.c = canvas
        self.mode = mode
        self.alive = False
        self.job = None
        self.particles = []

    def _init_particles(self):
        try:
            self.c.delete("fx")
        except Exception:
            pass
        self.particles.clear()
        if self.mode == "off":
            return
        w = max(900, self.c.winfo_width())
        h = max(660, self.c.winfo_height())
        if self.mode == "snow":
            for _ in range(75):
                r = random.uniform(1.2, 3.8)
                shade = int(140 + r * 28)
                color = f"#{shade:02x}{shade:02x}{shade:02x}"
                item = self.c.create_oval(0, 0, 0, 0, fill=color, outline="", tags="fx")
                self.particles.append({
                    "item": item, "x": random.uniform(0, w), "y": random.uniform(0, h),
                    "r": r, "vy": 0.7 + r * 0.4, "sway": random.uniform(0.3, 0.8),
                    "freq": random.uniform(0.8, 1.4), "phase": random.uniform(0, 6.28)
                })
        elif self.mode == "matrix":
            chars = "0123456789ABCDEF!#@*$%&"
            for _ in range(40):
                item = self.c.create_text(0, 0, text=random.choice(chars), fill="#00ff66",
                                          font=("Consolas", random.randint(10, 13), "bold"), tags="fx")
                self.particles.append({
                    "item": item, "x": random.uniform(10, w - 10), "y": random.uniform(0, h),
                    "vy": random.uniform(4, 9), "chars": chars
                })
        elif self.mode == "stars":
            for _ in range(85):
                r = random.uniform(0.8, 2.4)
                color = random.choice(["#ffffff", "#e0e7ff", "#fef08a", "#c7d2fe"])
                item = self.c.create_oval(0, 0, 0, 0, fill=color, outline="", tags="fx")
                self.particles.append({
                    "item": item, "x": random.uniform(0, w), "y": random.uniform(0, h),
                    "r": r, "vx": random.uniform(-0.25, 0.25), "vy": random.uniform(-0.25, 0.25)
                })
        elif self.mode == "neon":
            colors = ["#00f0ff", "#ff007f", "#7928ca", "#00dfd8", "#f5a623"]
            for _ in range(26):
                r = random.uniform(2.5, 6.0)
                col = random.choice(colors)
                item = self.c.create_oval(0, 0, 0, 0, fill=col, outline="", tags="fx")
                self.particles.append({
                    "item": item, "x": random.uniform(0, w), "y": random.uniform(0, h),
                    "r": r, "vx": random.uniform(-0.6, 0.6), "vy": random.uniform(-0.6, 0.6)
                })

    def set_mode(self, mode):
        self.mode = mode
        self._init_particles()

    def start(self):
        self.alive = True
        self._init_particles()
        self.tick()

    def stop(self):
        self.alive = False
        if self.job:
            try:
                self.c.after_cancel(self.job)
            except Exception:
                pass
            self.job = None

    def tick(self):
        if not self.alive:
            return
        if self.mode == "off":
            self.job = self.c.after(200, self.tick)
            return
        try:
            w = max(900, self.c.winfo_width())
            h = max(660, self.c.winfo_height())
            t = time.time()
            for p in self.particles:
                if self.mode == "snow":
                    p["y"] += p["vy"]
                    p["x"] += math.sin(t * p["freq"] + p["phase"]) * p["sway"]
                    if p["y"] > h + 10:
                        p["y"] = -10
                        p["x"] = random.uniform(0, w)
                    r = p["r"]
                    self.c.coords(p["item"], p["x"] - r, p["y"] - r, p["x"] + r, p["y"] + r)
                elif self.mode == "matrix":
                    p["y"] += p["vy"]
                    if p["y"] > h + 20:
                        p["y"] = -15
                        p["x"] = random.uniform(10, w - 10)
                    if random.random() < 0.12:
                        self.c.itemconfig(p["item"], text=random.choice(p["chars"]))
                    self.c.coords(p["item"], p["x"], p["y"])
                elif self.mode == "stars":
                    p["x"] = (p["x"] + p["vx"]) % w
                    p["y"] = (p["y"] + p["vy"]) % h
                    r = p["r"]
                    self.c.coords(p["item"], p["x"] - r, p["y"] - r, p["x"] + r, p["y"] + r)
                elif self.mode == "neon":
                    p["x"] = (p["x"] + p["vx"]) % w
                    p["y"] = (p["y"] + p["vy"]) % h
                    r = p["r"]
                    self.c.coords(p["item"], p["x"] - r, p["y"] - r, p["x"] + r, p["y"] + r)
            self.job = self.c.after(35, self.tick)
        except Exception:
            self.alive = False


# ═════════════════════════ GUI ═════════════════════════
def run_client():
    if winreg is None:
        raise SystemExit("Der Optimizer läuft nur unter Windows.")
    ensure(("customtkinter", "customtkinter"), ("requests", "requests"), ("psutil", "psutil"))
    import tkinter as tk

    import customtkinter as ctk

    class App(ctk.CTk):
        def __init__(self):
            super().__init__(fg_color=BG)
            ctk.set_appearance_mode("dark")
            self.title("REVOLT OPTIMIZER")
            self.geometry("900x660")
            self.minsize(860, 620)
            self.frame = None
            self.fx = None
            self.expires = None
            self.settings = load_settings()
            saved = load_key()
            self.show_license(prefill=saved, auto=bool(saved))

        def _canvas(self):
            c = tk.Canvas(self, bg=BG, highlightthickness=0, bd=0)
            return c, BackgroundFX(c, mode=self.settings.get("fx_mode", "snow"))

        def _swap(self, canvas, fx):
            if self.fx:
                self.fx.stop()
            if self.frame:
                self.frame.destroy()
            self.frame, self.fx = canvas, fx
            canvas.pack(fill="both", expand=True)
            fx.start()

        # ───── Lizenz-Screen ─────
        def show_license(self, prefill="", auto=False):
            c, fx = self._canvas()

            # Dezentes Gear-Icon oben rechts
            gear = ctk.CTkButton(c, text="⚙", width=36, height=36, corner_radius=8,
                                 fg_color="transparent", border_width=1, border_color=LINE2,
                                 text_color=MUTED, hover_color=ROW, font=("Segoe UI", 14),
                                 command=self.show_settings)
            gear.place(relx=1, x=-20, y=20, anchor="ne")

            # Zentrierte Login-Box
            box = ctk.CTkFrame(c, fg_color=CARD, border_color=LINE2, border_width=1, corner_radius=20,
                               width=420)
            box.place(relx=0.5, rely=0.5, anchor="center")
            box.pack_propagate(False)

            # Logo-Bereich
            top_area = ctk.CTkFrame(box, fg_color="transparent")
            top_area.pack(fill="x", padx=36, pady=(44, 0))

            ctk.CTkLabel(top_area, text="REVOLT", font=("Segoe UI", 32, "bold"),
                         text_color=FG).pack(anchor="w")
            ctk.CTkLabel(top_area, text="OPTIMIZER", font=("Segoe UI", 32, "bold"),
                         text_color=MUTED).pack(anchor="w")

            # Trennlinie
            ctk.CTkFrame(box, height=1, fg_color=LINE, corner_radius=0).pack(
                fill="x", padx=36, pady=(20, 24))

            # Mittelteil
            mid = ctk.CTkFrame(box, fg_color="transparent")
            mid.pack(fill="x", padx=36)

            ctk.CTkLabel(mid, text="Lizenzkey eingeben", font=("Segoe UI", 12),
                         text_color=MUTED).pack(anchor="w", pady=(0, 8))

            self.entry = ctk.CTkEntry(mid, width=348, height=46,
                                      placeholder_text="XXXX-XXXX-XXXX-XXXX",
                                      fg_color=ROW, border_color=LINE2, text_color=FG,
                                      justify="center", font=("Consolas", 15), corner_radius=10)
            self.entry.pack(fill="x")
            if prefill:
                self.entry.insert(0, prefill)

            self.status = ctk.CTkLabel(mid, text="", font=("Segoe UI", 12),
                                       text_color=MUTED, wraplength=340)
            self.status.pack(pady=(10, 0))

            self.btn = ctk.CTkButton(mid, text="Aktivieren →", height=46, corner_radius=10,
                                     fg_color=ACCENT, text_color="#000000",
                                     hover_color="#d8d8d8", font=("Segoe UI", 13, "bold"),
                                     command=self.activate)
            self.btn.pack(fill="x", pady=(12, 0))

            ctk.CTkFrame(box, height=36, fg_color="transparent").pack()

            self.entry.bind("<Return>", lambda _e: self.activate())
            self._swap(c, fx)
            if auto:
                self.after(200, self.activate)

        def activate(self):
            key = self.entry.get().strip().upper()
            if not key:
                self.status.configure(text="Bitte Key eingeben.", text_color=FG)
                return
            self.btn.configure(state="disabled", text="Prüfe …")
            self.status.configure(text="", text_color=MUTED)

            def work():
                ok, err, exp = check_license(key)
                self.after(0, lambda: self._after_check(ok, err, exp, key))

            threading.Thread(target=work, daemon=True).start()

        def _after_check(self, ok, err, exp, key):
            if ok:
                save_key(key)
                self.expires = exp
                self.show_main()
            else:
                self.btn.configure(state="normal", text="Aktivieren")
                self.status.configure(text=err, text_color=FG)

        # ───── Haupt-Screen ─────
        def show_main(self):
            c, fx = self._canvas()

            # ── Top-Bar ──
            c.create_text(28, 28, text="REVOLT OPTIMIZER", anchor="nw",
                          fill=FG, font=("Segoe UI", 20, "bold"))
            c.create_text(28, 58, text="FiveM Performance Suite",
                          anchor="nw", fill=MUTED, font=("Segoe UI", 11))

            exp_txt = time.strftime("%d.%m.%Y", time.localtime(self.expires)) if self.expires else "Lifetime"
            badge = ctk.CTkFrame(c, fg_color=ROW, border_color=LINE2, border_width=1, corner_radius=12)
            ctk.CTkLabel(badge, text=f"✦  Aktiv  ·  {exp_txt}",
                         font=("Segoe UI", 11), text_color=MUTED).pack(padx=14, pady=7)
            badge.place(relx=1, x=-24, y=24, anchor="ne")

            # ── Haupt-Container ──
            container = tk.Frame(c, bg=BG)
            container.place(x=24, y=84, relwidth=1.0, width=-48, relheight=1.0, height=-110)

            middle = tk.Frame(container, bg=BG)
            middle.pack(side="top", fill="both", expand=True, pady=(0, 10))

            # ── Linke Spalte: Tweaks ──
            left = ctk.CTkFrame(middle, fg_color=CARD, border_color=LINE, border_width=1, corner_radius=14)
            left.pack(side="left", fill="both", expand=True, padx=(0, 6))

            hdr = ctk.CTkFrame(left, fg_color="transparent")
            hdr.pack(fill="x", padx=16, pady=(14, 8))

            ctk.CTkLabel(hdr, text="OPTIMIERUNGEN", font=("Segoe UI", 10, "bold"),
                         text_color=MUTED).pack(side="left")
            self.count_lbl = ctk.CTkLabel(hdr, text="", font=("Segoe UI", 10), text_color=MUTED)
            self.count_lbl.pack(side="left", padx=8)
            self.toggle_btn = ctk.CTkButton(hdr, text="Alle abwählen", width=100, height=24,
                                            corner_radius=6, fg_color="transparent",
                                            border_width=1, border_color=LINE2,
                                            text_color=MUTED, hover_color=ROW,
                                            font=("Segoe UI", 10), command=self.toggle_all)
            self.toggle_btn.pack(side="right")

            # Trennlinie
            ctk.CTkFrame(left, height=1, fg_color=LINE, corner_radius=0).pack(fill="x", padx=0)

            scroll = ctk.CTkScrollableFrame(left, fg_color="transparent",
                                            scrollbar_button_color=LINE2,
                                            scrollbar_button_hover_color=MUTED)
            scroll.pack(fill="both", expand=True, padx=4, pady=4)

            self.switches, self.row_status = {}, {}
            for tid, title, desc, _fn in TWEAKS:
                row = ctk.CTkFrame(scroll, fg_color="transparent", corner_radius=10)
                row.pack(fill="x", padx=4, pady=2)

                # Hover-Effekt via Rahmen
                inner = ctk.CTkFrame(row, fg_color=ROW, border_color=LINE,
                                     border_width=1, corner_radius=10)
                inner.pack(fill="x")

                txt = ctk.CTkFrame(inner, fg_color="transparent")
                txt.pack(side="left", fill="x", expand=True, padx=(14, 6), pady=10)
                ctk.CTkLabel(txt, text=title, font=("Segoe UI", 13, "bold"),
                             text_color=FG, anchor="w").pack(fill="x")
                ctk.CTkLabel(txt, text=desc, font=("Segoe UI", 10), text_color=MUTED,
                             anchor="w", wraplength=280, justify="left").pack(fill="x")

                st = ctk.CTkLabel(inner, text="", width=20,
                                  font=("Segoe UI", 13, "bold"), text_color=FG)
                st.pack(side="right", padx=(0, 4))

                sw = ctk.CTkSwitch(inner, text="", width=42,
                                   progress_color=ACCENT, button_color=ACCENT,
                                   button_hover_color="#cccccc", fg_color=LINE2,
                                   command=self.update_count)
                sw.select()
                sw.pack(side="right", padx=(4, 12))
                self.switches[tid], self.row_status[tid] = sw, st

            # ── Rechte Spalte: Log ──
            right = ctk.CTkFrame(middle, fg_color=CARD, border_color=LINE,
                                 border_width=1, corner_radius=14, width=300)
            right.pack(side="right", fill="both", expand=False, padx=(6, 0))
            right.pack_propagate(False)

            ctk.CTkLabel(right, text="PROTOKOLL", font=("Segoe UI", 10, "bold"),
                         text_color=MUTED).pack(anchor="w", padx=16, pady=(14, 0))
            ctk.CTkFrame(right, height=1, fg_color=LINE, corner_radius=0).pack(
                fill="x", pady=(8, 0))

            self.log = ctk.CTkTextbox(right, fg_color="transparent", text_color=MUTED,
                                      border_width=0, font=("Consolas", 10),
                                      corner_radius=0, wrap="word")
            self.log.pack(fill="both", expand=True, padx=12, pady=(8, 12))
            self.log.configure(state="disabled")

            # ── Fortschrittsleiste ──
            self.progress = ctk.CTkProgressBar(container, height=2, corner_radius=1,
                                               fg_color=LINE, progress_color=ACCENT)
            self.progress.set(0)
            self.progress.pack(side="top", fill="x", pady=(0, 8))

            # ── Button-Reihe ──
            btn_row = tk.Frame(container, bg=BG)
            btn_row.pack(side="top", fill="x")

            self.run_btn = ctk.CTkButton(btn_row, text="▶  OPTIMIEREN", height=48,
                                         corner_radius=12, fg_color=ACCENT,
                                         text_color="#000000", hover_color="#d8d8d8",
                                         font=("Segoe UI", 13, "bold"), command=self.run_tweaks)
            self.run_btn.pack(side="left", fill="x", expand=True, padx=(0, 6))

            self.launch_btn = ctk.CTkButton(btn_row, text="🚀  FiveM", height=48,
                                            corner_radius=12, fg_color=ROW,
                                            border_width=1, border_color=LINE2,
                                            text_color=FG, hover_color="#1c1c1c",
                                            font=("Segoe UI", 12, "bold"),
                                            command=self.launch_fivem)
            self.launch_btn.pack(side="left", padx=(0, 6))

            self.settings_btn = ctk.CTkButton(btn_row, text="⚙", width=48, height=48,
                                              corner_radius=12, fg_color=ROW,
                                              border_width=1, border_color=LINE2,
                                              text_color=MUTED, hover_color="#1c1c1c",
                                              font=("Segoe UI", 15), command=self.show_settings)
            self.settings_btn.pack(side="right")

            self._swap(c, fx)
            self.update_count()
            self.write("Bereit. Wähle Optimierungen und starte.")

        # ───── Einstellungs-Screen ─────
        def show_settings(self):
            c, fx = self._canvas()

            c.create_text(28, 28, text="EINSTELLUNGEN", anchor="nw",
                          fill=FG, font=("Segoe UI", 20, "bold"))
            c.create_text(28, 58, text="Personalisierung & Lizenzinfo",
                          anchor="nw", fill=MUTED, font=("Segoe UI", 11))

            has_key = bool(self.expires or load_key())
            back_cmd = self.show_main if has_key else self.show_license
            back_text = "← Zurück" if has_key else "← Anmeldung"

            back_btn = ctk.CTkButton(c, text=back_text, width=110, height=34, corner_radius=8,
                                     fg_color="transparent", border_width=1, border_color=LINE2,
                                     text_color=MUTED, hover_color=ROW,
                                     font=("Segoe UI", 11), command=back_cmd)
            back_btn.place(relx=1, x=-24, y=28, anchor="ne")

            container = tk.Frame(c, bg=BG)
            container.place(x=24, y=84, relwidth=1.0, width=-48, relheight=1.0, height=-100)

            scroll = ctk.CTkScrollableFrame(container, fg_color="transparent",
                                            scrollbar_button_color=LINE2,
                                            scrollbar_button_hover_color=MUTED)
            scroll.pack(fill="both", expand=True)

            def section_header(parent, text):
                ctk.CTkLabel(parent, text=text, font=("Segoe UI", 10, "bold"),
                             text_color=MUTED).pack(anchor="w", padx=4, pady=(18, 6))

            def option_row(parent, title, desc, right_widget_fn):
                row = ctk.CTkFrame(parent, fg_color=CARD, border_color=LINE,
                                   border_width=1, corner_radius=12)
                row.pack(fill="x", pady=3)
                txt = ctk.CTkFrame(row, fg_color="transparent")
                txt.pack(side="left", fill="x", expand=True, padx=(16, 8), pady=12)
                ctk.CTkLabel(txt, text=title, font=("Segoe UI", 12, "bold"),
                             text_color=FG, anchor="w").pack(fill="x")
                ctk.CTkLabel(txt, text=desc, font=("Segoe UI", 10), text_color=MUTED,
                             anchor="w").pack(fill="x")
                right_widget_fn(row)

            # ── 1. Hintergrund-Animation ──
            section_header(scroll, "HINTERGRUND-EFFEKTE")

            fx_options = [
                ("snow",   "❄  Schneeflocken",         "Sanft tanzender weißer Schnee"),
                ("matrix", "▓  Matrix Code-Regen",     "Grüne digitale Ziffern im Hacker-Style"),
                ("stars",  "✦  Sternenstaub",           "Schwebende funkelnde Sterne"),
                ("neon",   "◉  Neon Orbs",              "Farbige Cyberpunk-Lichtkugeln"),
                ("off",    "○  Ausgeschaltet",          "Pures Schwarz, 0% CPU"),
            ]

            cur_mode = self.settings.get("fx_mode", "snow")
            self.fx_var = tk.StringVar(value=cur_mode)

            def on_fx_change(new_val):
                self.settings["fx_mode"] = new_val
                save_settings(self.settings)
                if self.fx:
                    self.fx.set_mode(new_val)

            for val, title, desc in fx_options:
                def make_rb(parent, v=val):
                    rb = ctk.CTkRadioButton(parent, text="", value=v, variable=self.fx_var,
                                            command=lambda vv=v: on_fx_change(vv),
                                            fg_color=ACCENT, hover_color="#cccccc",
                                            border_color=LINE2)
                    rb.pack(side="right", padx=16)
                option_row(scroll, title, desc, make_rb)

            # ── 2. Audio ──
            section_header(scroll, "AUDIO")

            def make_sound_sw(parent):
                def on_toggle():
                    self.settings["play_sound"] = bool(self.sound_sw.get())
                    save_settings(self.settings)
                self.sound_sw = ctk.CTkSwitch(parent, text="", width=42,
                                              progress_color=ACCENT, button_color=ACCENT,
                                              button_hover_color="#cccccc", fg_color=LINE2,
                                              command=on_toggle)
                if self.settings.get("play_sound", True):
                    self.sound_sw.select()
                else:
                    self.sound_sw.deselect()
                self.sound_sw.pack(side="right", padx=16)

            option_row(scroll, "Erfolgs-Sound",
                       "Spielt einen Ton ab, wenn alle Optimierungen fertig sind.",
                       make_sound_sw)

            # ── 3. Lizenz-Infos ──
            section_header(scroll, "LIZENZ")

            key_val = load_key() or "Kein Key gespeichert"
            exp_val = time.strftime("%d.%m.%Y", time.localtime(self.expires)) if self.expires else "Lifetime"

            info_card = ctk.CTkFrame(scroll, fg_color=CARD, border_color=LINE,
                                     border_width=1, corner_radius=12)
            info_card.pack(fill="x", pady=3)

            for label, value in [("Lizenzkey", key_val), ("Gültig bis", exp_val), ("HWID", get_hwid())]:
                info_row = ctk.CTkFrame(info_card, fg_color="transparent")
                info_row.pack(fill="x", padx=16, pady=(10, 0))
                ctk.CTkLabel(info_row, text=label, font=("Segoe UI", 10),
                             text_color=MUTED).pack(side="left")
                ctk.CTkLabel(info_row, text=value, font=("Consolas", 10),
                             text_color=FG).pack(side="right")
            ctk.CTkFrame(info_card, height=10, fg_color="transparent").pack()

            ctk.CTkFrame(scroll, height=4, fg_color="transparent").pack()

            def on_relogin():
                save_key("")
                self.expires = None
                self.show_license()

            ctk.CTkButton(scroll, text="Abmelden & anderen Key eingeben", height=40,
                          corner_radius=10, fg_color="transparent",
                          border_width=1, border_color=LINE2,
                          text_color=MUTED, hover_color=ROW,
                          font=("Segoe UI", 11), command=on_relogin).pack(fill="x", pady=(4, 20))

            self._swap(c, fx)

        def launch_fivem(self):
            exe = os.path.join(fivem_dir(), "FiveM.exe")
            if os.path.isfile(exe):
                try:
                    os.startfile(exe)
                    self.write("🚀 FiveM wird gestartet … Viel Spaß!")
                except Exception as e:
                    self.write(f"Fehler beim Starten: {e}")
            else:
                self.write("FiveM.exe im Standardordner (%LOCALAPPDATA%\\FiveM) nicht gefunden.")

        def update_count(self):
            n = sum(1 for sw in self.switches.values() if sw.get())
            self.count_lbl.configure(text=f"{n} von {len(self.switches)} aktiv")
            self.toggle_btn.configure(text="Alle abwählen" if n == len(self.switches) else "Alle auswählen")

        def toggle_all(self):
            all_on = all(sw.get() for sw in self.switches.values())
            for sw in self.switches.values():
                sw.deselect() if all_on else sw.select()
            self.update_count()

        def write(self, text):
            self.log.configure(state="normal")
            self.log.insert("end", f"[{time.strftime('%H:%M:%S')}] {text}\n")
            self.log.see("end")
            self.log.configure(state="disabled")

        def run_tweaks(self):
            chosen = [t for t in TWEAKS if self.switches[t[0]].get()]
            if not chosen:
                self.write("Keine Optimierung ausgewählt.")
                return
            self.run_btn.configure(state="disabled", text="LÄUFT …")
            self.progress.set(0)
            for st in self.row_status.values():
                st.configure(text="")
            for t in chosen:
                self.row_status[t[0]].configure(text="…", text_color=MUTED)

            def work():
                total = len(chosen)
                for i, (tid, title, _d, fn) in enumerate(chosen, 1):
                    try:
                        msg, ok = fn(), True
                    except Exception as e:  # noqa: BLE001
                        msg, ok = f"{title}: Fehler ({e})", False
                    self.after(0, lambda m=msg, t=tid, o=ok, n=i: self._step_done(m, t, o, n, total))
                self.after(0, self._finished)

            threading.Thread(target=work, daemon=True).start()

        def _step_done(self, msg, tid, ok, n, total):
            self.write(msg)
            self.row_status[tid].configure(text="✓" if ok else "✕", text_color=FG)
            self.progress.set(n / total)

        def _finished(self):
            self.write("Fertig ✔ – starte FiveM neu, damit alles greift.")
            self.run_btn.configure(state="normal", text="OPTIMIEREN")
            if self.settings.get("play_sound", True):
                try:
                    import winsound
                    winsound.MessageBeep(winsound.MB_OK)
                except Exception:
                    pass

    App().mainloop()


# ═════════════════════════ START ═════════════════════════
def main():
    mode = sys.argv[1].lower() if len(sys.argv) > 1 else "client"
    if mode in ("server", "admin"):
        run_server(ask_password())
    elif mode in ("both", "test"):
        pw = ask_password()
        ensure(("flask", "flask"))
        threading.Thread(target=run_server, args=(pw,), daemon=True).start()
        time.sleep(1.5)
        run_client()
    else:
        run_client()


if __name__ == "__main__":
    main()
