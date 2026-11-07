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
SERVER_URL = "http://5.253.246.114:5050"
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
        c.execute(
            """CREATE TABLE IF NOT EXISTS users(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                name TEXT NOT NULL,
                avatar TEXT DEFAULT '',
                discord TEXT DEFAULT '',
                license_id INTEGER,
                created_at INTEGER NOT NULL,
                last_login INTEGER)"""
        )
        user_columns = {row["name"] for row in c.execute("PRAGMA table_info(users)").fetchall()}
        if "is_active" not in user_columns:
            c.execute("ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")


def new_key():
    return "-".join("".join(secrets.choice(KEY_ALPHABET) for _ in range(4)) for _ in range(4))


def fmt_ts(ts):
    return time.strftime("%d.%m.%Y %H:%M", time.localtime(ts)) if ts else "–"


STYLE = """
<style>
:root{color-scheme:dark;--bg:#05070b;--card:rgba(13,16,22,.88);--row:#111821;--line:#202a35;--line2:#344252;--fg:#f5f8fc;--muted:#8b98a8;--ice:#8ceaff;--ice-soft:rgba(70,205,255,.12)}
*{box-sizing:border-box}
html,body{margin:0;min-height:100%}
body{background:radial-gradient(ellipse at 18% -8%,rgba(22,101,130,.18),transparent 38%),radial-gradient(ellipse at 100% 22%,rgba(35,61,119,.12),transparent 34%),var(--bg);color:var(--fg);font-family:Inter,"Segoe UI",system-ui,sans-serif;overflow-x:hidden}
canvas#snow{position:fixed;inset:0;width:100%;height:100%;pointer-events:none;z-index:0;opacity:.62;mix-blend-mode:screen}
.wrap{position:relative;z-index:1;max-width:1080px;margin:0 auto;padding:34px 20px 70px;animation:pageIn .75s cubic-bezier(.2,.7,.2,1) both}
h1{font-size:25px;letter-spacing:.2em;margin:0;font-weight:850;background:linear-gradient(100deg,#fff 0%,#d7f8ff 58%,#8ceaff 100%);-webkit-background-clip:text;background-clip:text;color:transparent}
.sub{color:var(--muted);font-size:13px;margin-top:6px}
.top{display:flex;justify-content:space-between;align-items:center;margin-bottom:26px;gap:12px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:20px}
.stat{position:relative;overflow:hidden;background:linear-gradient(145deg,rgba(18,24,33,.94),rgba(8,11,16,.94));border:1px solid var(--line);border-radius:16px;padding:17px 19px;box-shadow:0 12px 30px rgba(0,0,0,.22);transition:transform .24s,border-color .24s,box-shadow .24s;animation:cardIn .65s both}
.stat:after{content:"";position:absolute;inset:auto -30% -75% 20%;height:100%;background:radial-gradient(ellipse,var(--ice-soft),transparent 68%);pointer-events:none}
.stat:hover{transform:translateY(-4px);border-color:#426174;box-shadow:0 18px 38px rgba(0,0,0,.34),0 0 24px rgba(90,210,255,.07)}
.stat b{position:relative;z-index:1;display:block;font-size:29px;margin-bottom:2px;letter-spacing:-.04em}
.stat span{position:relative;z-index:1;color:var(--muted);font-size:12px}
.card{background:linear-gradient(145deg,rgba(15,19,26,.94),rgba(8,11,16,.93));border:1px solid var(--line);border-radius:18px;padding:21px;margin-bottom:20px;box-shadow:0 18px 44px rgba(0,0,0,.28);backdrop-filter:blur(14px);transition:border-color .25s,transform .25s,box-shadow .25s;animation:cardIn .7s both}
.wrap>.card:hover{border-color:#2d4050;box-shadow:0 20px 48px rgba(0,0,0,.36),0 0 30px rgba(70,205,255,.035)}
.card h2{font-size:13px;margin:0 0 15px;letter-spacing:.11em;color:#eaf6fc}
input,select{background:rgba(3,6,10,.82);border:1px solid var(--line);color:var(--fg);padding:12px 14px;border-radius:11px;font-size:14px;font-family:inherit;transition:border-color .2s,box-shadow .2s,background .2s}
input:focus,select:focus{outline:none;border-color:#6eddf5;box-shadow:0 0 0 3px rgba(88,205,235,.12);background:#080d13}
button{position:relative;overflow:hidden;background:linear-gradient(120deg,#f8fdff,#b9f0ff);color:#071017;border:0;padding:11px 18px;border-radius:11px;font-weight:750;cursor:pointer;font-family:inherit;transition:transform .18s,box-shadow .22s,filter .22s}
button:before{content:"";position:absolute;top:-80%;left:-45%;width:28%;height:260%;background:rgba(255,255,255,.6);transform:rotate(25deg);transition:left .5s ease}
button:hover{transform:translateY(-2px);box-shadow:0 8px 20px rgba(90,210,255,.16);filter:brightness(1.04)}
button:hover:before{left:130%}
button:active{transform:translateY(0) scale(.98)}
button.ghost{background:rgba(255,255,255,.02);color:#e8f7fc;border:1px solid var(--line2)}
button.ghost:before{display:none}
button.ghost:hover{border-color:#6eddf5;background:rgba(70,205,255,.06);box-shadow:0 6px 18px rgba(70,205,255,.08)}
button.sm{padding:7px 11px;font-size:12px;border-radius:9px}
form.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.grow{flex:1;min-width:180px}
.toolbar{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px}
.tablewrap{overflow:auto;border:1px solid var(--line);border-radius:12px;background:rgba(3,5,8,.32)}
table{width:100%;border-collapse:collapse;font-size:13px}
th{color:#93a5b4;text-align:left;font-weight:600;padding:12px 10px;border-bottom:1px solid var(--line);white-space:nowrap;background:rgba(255,255,255,.025)}
td{padding:12px 10px;border-bottom:1px solid rgba(32,42,53,.75);vertical-align:middle;transition:background .18s}
tr{animation:rowIn .36s ease both}
tr:last-child td{border-bottom:0}
tbody tr:hover td{background:rgba(76,194,230,.045)}
code{font-family:Consolas,monospace;font-size:14px;letter-spacing:.04em;color:#d4f8ff}
.tag{display:inline-flex;align-items:center;gap:5px;border:1px solid var(--line2);border-radius:999px;padding:4px 10px;font-size:11px;color:#a9b7c3;white-space:nowrap;background:rgba(255,255,255,.025)}
.tag.ok{color:#9af5d2;border-color:rgba(85,232,174,.35);background:rgba(53,202,140,.09);box-shadow:0 0 14px rgba(64,222,160,.08)}
.err{color:#ffd5dd;border:1px solid rgba(255,105,132,.4);background:rgba(255,74,106,.08);border-radius:11px;padding:12px;margin-bottom:12px;animation:shakeIn .35s ease both}
.actions{display:flex;gap:6px;flex-wrap:nowrap}
.actions form{margin:0}
.newkeys{border-color:rgba(113,224,255,.42);box-shadow:0 0 30px rgba(70,205,255,.1),0 18px 44px rgba(0,0,0,.28)}
.keyline{display:flex;align-items:center;gap:10px;padding:10px 0;border-bottom:1px solid var(--line);animation:rowIn .4s ease both}
.keyline:last-of-type{border-bottom:0}
.keyline code{font-size:17px;flex:1}
.empty{color:var(--muted);text-align:center;padding:28px 0}
.toast{position:fixed;left:50%;bottom:28px;transform:translateX(-50%) translateY(18px);background:linear-gradient(120deg,#e5fbff,#fff);color:#071017;padding:11px 18px;border-radius:12px;font-weight:750;font-size:13px;opacity:0;transition:opacity .24s,transform .24s;z-index:5;pointer-events:none;box-shadow:0 14px 36px rgba(0,0,0,.4)}
.toast.on{opacity:1;transform:translateX(-50%) translateY(0)}
@keyframes pageIn{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}
@keyframes cardIn{from{opacity:0;transform:translateY(13px) scale(.99)}to{opacity:1;transform:translateY(0) scale(1)}}
@keyframes rowIn{from{opacity:0;transform:translateX(-5px)}to{opacity:1;transform:translateX(0)}}
@keyframes shakeIn{0%{opacity:0;transform:translateX(-5px)}60%{transform:translateX(3px)}100%{opacity:1;transform:translateX(0)}}
@media(max-width:640px){h1{font-size:19px}.wrap{padding:22px 13px 50px}.card{padding:16px;border-radius:15px}.stats{grid-template-columns:repeat(2,minmax(0,1fr))}.stat{padding:14px}.stat b{font-size:24px}.actions{flex-wrap:wrap}}
@media(prefers-reduced-motion:reduce){*,*:before,*:after{animation-duration:.01ms!important;animation-iteration-count:1!important;scroll-behavior:auto!important;transition-duration:.01ms!important}}
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

    # ───── Benutzer-Passwort & Auth Helpers ─────
    def hash_password(password):
        salt = secrets.token_hex(16)
        h = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000).hex()
        return f"{salt}:{h}"

    def verify_password(password, stored_hash):
        if not stored_hash or ":" not in stored_hash:
            return False
        salt, h = stored_hash.split(":", 1)
        check = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000).hex()
        return hmac.compare_digest(check, h)

    def make_user_token(uid):
        exp = int(time.time()) + 30 * 86400  # 30 Tage gültig
        raw = f"usr:{uid}:{exp}"
        sig = hmac.new(app.secret_key.encode(), raw.encode(), hashlib.sha256).hexdigest()
        return f"{raw}:{sig}"

    def verify_user_token(tok):
        if not tok or not tok.startswith("usr:"):
            return None
        parts = tok.split(":")
        if len(parts) != 4:
            return None
        _, uid_str, exp_str, sig = parts
        try:
            uid, exp = int(uid_str), int(exp_str)
        except ValueError:
            return None
        if exp < time.time():
            return None
        expected = hmac.new(app.secret_key.encode(), f"usr:{uid}:{exp}".encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        return uid

    def api_user_required(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            auth = request.headers.get("Authorization", "")
            tok = auth.replace("Bearer ", "").strip() if auth.startswith("Bearer ") else None
            uid = verify_user_token(tok)
            if not uid:
                return jsonify(success=False, error="Nicht eingeloggt oder Sitzung abgelaufen."), 401
            with db() as c:
                u = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
            if not u:
                return jsonify(success=False, error="Benutzerkonto nicht gefunden."), 404
            if not u["is_active"]:
                return jsonify(success=False, error="Dein Konto wurde vom Administrator gesperrt."), 403
            return fn(dict(u), *a, **kw)
        return wrapper

    def serialize_user(u):
        lic = None
        if u.get("license_id"):
            with db() as c:
                l = c.execute("SELECT * FROM licenses WHERE id=?", (u["license_id"],)).fetchone()
            if l:
                now = int(time.time())
                if l["revoked"]:
                    st = "gesperrt"
                elif l["expires_at"] and l["expires_at"] < now:
                    st = "abgelaufen"
                else:
                    st = "aktiv"
                lic = {
                    "id": l["id"],
                    "key": l["key"],
                    "note": l["note"] or "",
                    "created_at": l["created_at"],
                    "expires_at": l["expires_at"],
                    "hwid": l["hwid"],
                    "bound": bool(l["hwid"]),
                    "status": st
                }
        return {
            "id": u["id"],
            "name": u["name"],
            "email": u["email"],
            "avatar": u["avatar"] or "",
            "discord": u["discord"] or "",
            "created_at": u["created_at"],
            "last_login": u["last_login"],
            "license": lic
        }

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

    @app.get("/api/admin/users")
    @api_admin_required
    def api_admin_users_list():
        now = int(time.time())
        with db() as c:
            rows = c.execute("""SELECT u.id,u.name,u.email,u.created_at,u.last_login,u.discord,
                               u.license_id,u.is_active,l.key,l.expires_at,l.revoked
                               FROM users u LEFT JOIN licenses l ON l.id=u.license_id
                               ORDER BY u.id DESC""").fetchall()
        users = []
        for row in rows:
            license_info = None
            if row["license_id"] and row["key"]:
                status = "gesperrt" if row["revoked"] else (
                    "abgelaufen" if row["expires_at"] and row["expires_at"] < now else "aktiv")
                license_info = {"key": row["key"], "status": status, "expires_at": row["expires_at"]}
            users.append({
                "id": row["id"], "name": row["name"], "email": row["email"],
                "created_at": row["created_at"], "last_login": row["last_login"],
                "discord": row["discord"] or "", "is_active": bool(row["is_active"]),
                "status": "aktiv" if row["is_active"] else "gesperrt", "license": license_info,
            })
        return jsonify(success=True, users=users, stats={
            "total": len(users), "active": sum(u["is_active"] for u in users),
            "suspended": sum(not u["is_active"] for u in users),
        })

    @app.route("/api/admin/users/<int:user_id>", methods=["PUT", "PATCH"])
    @api_admin_required
    def api_admin_user_update(user_id):
        data = request.get_json(silent=True) or {}
        with db() as c:
            user = c.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
            if not user:
                return jsonify(success=False, error="Benutzer nicht gefunden."), 404
            name = str(data.get("name", user["name"])).strip()
            email = str(data.get("email", user["email"])).strip().lower()
            if not name or len(name) > 40:
                return jsonify(success=False, error="Der Name muss 1 bis 40 Zeichen lang sein."), 400
            if not email or len(email) > 100 or "@" not in email:
                return jsonify(success=False, error="Bitte gib eine gültige E-Mail-Adresse ein."), 400
            try:
                c.execute("UPDATE users SET name=?,email=? WHERE id=?", (name, email, user_id))
            except sqlite3.IntegrityError:
                return jsonify(success=False, error="Diese E-Mail-Adresse ist bereits registriert."), 409
        return jsonify(success=True)

    @app.post("/api/admin/users/<int:user_id>/toggle")
    @api_admin_required
    def api_admin_user_toggle(user_id):
        with db() as c:
            user = c.execute("SELECT is_active FROM users WHERE id=?", (user_id,)).fetchone()
            if not user:
                return jsonify(success=False, error="Benutzer nicht gefunden."), 404
            active = 1 - user["is_active"]
            c.execute("UPDATE users SET is_active=? WHERE id=?", (active, user_id))
        return jsonify(success=True, is_active=bool(active))

    @app.delete("/api/admin/users/<int:user_id>")
    @api_admin_required
    def api_admin_user_delete(user_id):
        with db() as c:
            user = c.execute("SELECT id FROM users WHERE id=?", (user_id,)).fetchone()
            if not user:
                return jsonify(success=False, error="Benutzer nicht gefunden."), 404
            c.execute("DELETE FROM users WHERE id=?", (user_id,))
        return jsonify(success=True)

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
            c.execute("UPDATE users SET license_id=NULL WHERE license_id=?", (lid,))
            c.execute("DELETE FROM licenses WHERE id=?", (lid,))
        return jsonify(success=True)

    # ───── Kunden-Portal API (/api/auth, /api/me, /api/download) ─────
    @app.post("/api/auth/register")
    def api_auth_register():
        if rate_limited("reg:" + str(request.remote_addr)):
            return jsonify(success=False, error="Zu viele Versuche, bitte kurz warten."), 429
        data = request.get_json(silent=True) or {}
        name = str(data.get("name", "")).strip()[:40]
        email = str(data.get("email", "")).strip().lower()[:100]
        password = str(data.get("password", ""))
        if not name:
            return jsonify(success=False, error="Bitte einen Namen eingeben."), 400
        if not email or "@" not in email:
            return jsonify(success=False, error="Bitte eine gültige E-Mail-Adresse eingeben."), 400
        if len(password) < 8:
            return jsonify(success=False, error="Das Passwort muss mindestens 8 Zeichen lang sein."), 400
        now = int(time.time())
        pw_hash = hash_password(password)
        try:
            with db() as c:
                cur = c.execute(
                    "INSERT INTO users(name, email, password_hash, created_at, last_login) VALUES(?,?,?,?,?)",
                    (name, email, pw_hash, now, now)
                )
                uid = cur.lastrowid
                u = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        except sqlite3.IntegrityError:
            return jsonify(success=False, error="Diese E-Mail-Adresse ist bereits registriert."), 400
        tok = make_user_token(uid)
        return jsonify(success=True, token=tok, user=serialize_user(dict(u)))

    @app.post("/api/auth/login")
    def api_auth_login():
        if rate_limited("userlogin:" + str(request.remote_addr)):
            return jsonify(success=False, error="Zu viele Versuche, bitte kurz warten."), 429
        data = request.get_json(silent=True) or {}
        email = str(data.get("email", "")).strip().lower()
        password = str(data.get("password", ""))
        if not email or not password:
            return jsonify(success=False, error="Bitte E-Mail und Passwort eingeben."), 400
        with db() as c:
            u = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if not u or not verify_password(password, u["password_hash"]):
            return jsonify(success=False, error="Falsche E-Mail-Adresse oder falsches Passwort."), 401
        if not u["is_active"]:
            return jsonify(success=False, error="Dein Konto wurde vom Administrator gesperrt."), 403
        now = int(time.time())
        with db() as c:
            c.execute("UPDATE users SET last_login=? WHERE id=?", (now, u["id"]))
        u_dict = dict(u)
        u_dict["last_login"] = now
        tok = make_user_token(u["id"])
        return jsonify(success=True, token=tok, user=serialize_user(u_dict))

    @app.get("/api/me")
    @api_user_required
    def api_get_me(user):
        return jsonify(success=True, user=serialize_user(user))

    @app.patch("/api/me")
    @api_user_required
    def api_patch_me(user):
        data = request.get_json(silent=True) or {}
        name = str(data.get("name", user["name"])).strip()[:40]
        email = str(data.get("email", user["email"])).strip().lower()[:100]
        discord = str(data.get("discord", user["discord"] or "")).strip()[:40]
        avatar = user["avatar"]
        if "avatar" in data:
            avatar = str(data.get("avatar") or "")
            if len(avatar) > 600000:
                return jsonify(success=False, error="Avatar-Bild ist zu groß (max. 500 KB)."), 400
        if not name:
            return jsonify(success=False, error="Name darf nicht leer sein."), 400
        if not email or "@" not in email:
            return jsonify(success=False, error="Ungültige E-Mail-Adresse."), 400
        try:
            with db() as c:
                c.execute(
                    "UPDATE users SET name=?, email=?, discord=?, avatar=? WHERE id=?",
                    (name, email, discord, avatar, user["id"])
                )
                updated = c.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone()
        except sqlite3.IntegrityError:
            return jsonify(success=False, error="Diese E-Mail-Adresse wird bereits verwendet."), 400
        return jsonify(success=True, user=serialize_user(dict(updated)))

    @app.post("/api/me/password")
    @api_user_required
    def api_me_password(user):
        data = request.get_json(silent=True) or {}
        current_pw = str(data.get("current", ""))
        new_pw = str(data.get("new", ""))
        if not verify_password(current_pw, user["password_hash"]):
            return jsonify(success=False, error="Das aktuelle Passwort ist nicht korrekt."), 400
        if len(new_pw) < 8:
            return jsonify(success=False, error="Neues Passwort muss mindestens 8 Zeichen lang sein."), 400
        new_hash = hash_password(new_pw)
        with db() as c:
            c.execute("UPDATE users SET password_hash=? WHERE id=?", (new_hash, user["id"]))
        return jsonify(success=True)

    @app.post("/api/me/license")
    @api_user_required
    def api_me_license(user):
        data = request.get_json(silent=True) or {}
        key = str(data.get("key", "")).strip().upper()
        if not KEY_RE.match(key):
            return jsonify(success=False, error="Ungültiges Key-Format (XXXX-XXXX-XXXX-XXXX)."), 400
        with db() as c:
            lic = c.execute("SELECT * FROM licenses WHERE key=?", (key,)).fetchone()
            if not lic:
                return jsonify(success=False, error="Lizenzkey nicht gefunden."), 404
            taken = c.execute("SELECT id FROM users WHERE license_id=? AND id != ?", (lic["id"], user["id"])).fetchone()
            if taken:
                return jsonify(success=False, error="Dieser Key ist bereits mit einem anderen Konto verknüpft."), 400
            c.execute("UPDATE users SET license_id=? WHERE id=?", (lic["id"], user["id"]))
            updated = c.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone()
        return jsonify(success=True, user=serialize_user(dict(updated)))

    @app.delete("/api/me/license")
    @api_user_required
    def api_me_license_detach(user):
        with db() as c:
            c.execute("UPDATE users SET license_id=NULL WHERE id=?", (user["id"],))
            updated = c.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone()
        return jsonify(success=True, user=serialize_user(dict(updated)))

    @app.delete("/api/me")
    @api_user_required
    def api_me_delete(user):
        data = request.get_json(silent=True) or {}
        pw = str(data.get("password", ""))
        if not verify_password(pw, user["password_hash"]):
            return jsonify(success=False, error="Passwort ist nicht korrekt."), 400
        with db() as c:
            c.execute("DELETE FROM users WHERE id=?", (user["id"],))
        return jsonify(success=True)

    @app.get("/api/download/info")
    def api_download_info():
        target_name = "revolt.py"
        for cand in ("revolt.exe", "fivem_boost.exe", "revolt.py", "fivem_boost.py"):
            p = os.path.join(BASE_DIR, cand)
            if os.path.isfile(p):
                target_name = cand
                break
        target_path = os.path.join(BASE_DIR, target_name)
        exists = os.path.isfile(target_path)
        size = os.path.getsize(target_path) if exists else 0
        mtime = int(os.path.getmtime(target_path)) if exists else int(time.time())
        return jsonify(
            success=True,
            available=exists,
            version="2.0",
            filename=target_name,
            size=size,
            updated=mtime,
            updated_at=mtime
        )

    @app.get("/api/download/client")
    def api_download_client():
        from flask import send_file
        target_name = "revolt.py"
        for cand in ("revolt.exe", "fivem_boost.exe", "revolt.py", "fivem_boost.py"):
            p = os.path.join(BASE_DIR, cand)
            if os.path.isfile(p):
                target_name = cand
                break
        target_path = os.path.join(BASE_DIR, target_name)
        if not os.path.isfile(target_path):
            return jsonify(success=False, error="Download-Datei noch nicht auf dem Server abgelegt."), 404
        return send_file(target_path, as_attachment=True, download_name=target_name)

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
        # Falls portal.html oder lizenzverwaltung.html existiert, liefere sie aus
        for fname in ("portal.html", "lizenzverwaltung.html"):
            html_path = os.path.join(BASE_DIR, fname)
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

    @app.route("/portal")
    @app.route("/")
    def index():
        for fname in ("portal.html", "lizenzverwaltung.html"):
            p = os.path.join(BASE_DIR, fname)
            if os.path.isfile(p):
                with open(p, "r", encoding="utf-8") as f:
                    return f.read()
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
        elif self.mode == "comet":
            colors = ["#8ceaff", "#c4f5ff", "#ffffff", "#80aaff"]
            for _ in range(16):
                vx = random.uniform(2.0, 4.2)
                vy = random.uniform(0.45, 1.35)
                tail = random.uniform(18, 44)
                item = self.c.create_line(0, 0, 0, 0, fill=random.choice(colors),
                                          width=random.choice([1, 2]), capstyle="round", tags="fx")
                self.particles.append({
                    "item": item, "x": random.uniform(-w, w), "y": random.uniform(-h, h),
                    "vx": vx, "vy": vy, "tail": tail
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
                elif self.mode == "comet":
                    p["x"] += p["vx"]
                    p["y"] += p["vy"]
                    if p["x"] > w + p["tail"] or p["y"] > h + p["tail"]:
                        p["x"] = random.uniform(-w * 0.4, -p["tail"])
                        p["y"] = random.uniform(-h * 0.4, h * 0.8)
                    self.c.coords(p["item"], p["x"] - p["tail"], p["y"] - p["tail"] * 0.28,
                                  p["x"], p["y"])
            self.job = self.c.after(35, self.tick)
        except Exception:
            self.alive = False


# ═════════════════════════ GUI ═════════════════════════
LOGO_B64 = "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"

def get_app_logo(size=(48, 48)):
    try:
        import base64, io
        from PIL import Image
        import customtkinter as ctk
        raw = base64.b64decode(LOGO_B64)
        im = Image.open(io.BytesIO(raw))
        return ctk.CTkImage(light_image=im, dark_image=im, size=size)
    except Exception:
        return None


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
            self._progress_job = None
            self._progress_value = 0.0
            self.settings = load_settings()
            self._fade_alpha = 0.0
            self._fade_enabled = True
            try:
                self.attributes("-alpha", 0.0)
            except Exception:
                self._fade_alpha = 1.0
                self._fade_enabled = False
            saved = load_key()
            self.show_license(prefill=saved, auto=bool(saved))
            if self._fade_enabled:
                self.after(18, self._fade_in)

        def _fade_in(self):
            self._fade_alpha = min(1.0, self._fade_alpha + 0.08)
            try:
                self.attributes("-alpha", self._fade_alpha)
            except Exception:
                self._fade_enabled = False
                return
            if self._fade_alpha < 1.0:
                self.after(16, self._fade_in)

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
            box = ctk.CTkFrame(c, fg_color=CARD, border_color=LINE2, border_width=1, corner_radius=20)
            box.place(relx=0.5, rely=0.5, anchor="center")

            # Logo-Bereich
            top_area = ctk.CTkFrame(box, fg_color="transparent")
            top_area.pack(fill="x", padx=36, pady=(36, 0))

            logo_img = get_app_logo((56, 56))
            if logo_img:
                self.lic_logo = logo_img
                ctk.CTkLabel(top_area, image=logo_img, text="").pack(side="left", padx=(0, 16))

            titles = ctk.CTkFrame(top_area, fg_color="transparent")
            titles.pack(side="left")
            ctk.CTkLabel(titles, text="REVOLT", font=("Segoe UI", 26, "bold"),
                         text_color=FG).pack(anchor="w")
            ctk.CTkLabel(titles, text="OPTIMIZER", font=("Segoe UI", 26, "bold"),
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
            logo_img = get_app_logo((38, 38))
            if logo_img:
                self.main_logo = logo_img
                logo_lbl = ctk.CTkLabel(c, image=logo_img, text="", fg_color="transparent")
                logo_lbl.place(x=24, y=24)
                c.create_text(72, 25, text="REVOLT OPTIMIZER", anchor="nw",
                              fill=FG, font=("Segoe UI", 20, "bold"))
                c.create_text(72, 53, text="FiveM Performance Suite",
                              anchor="nw", fill=MUTED, font=("Segoe UI", 11))
            else:
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
            self._progress_value = 0.0
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
                ("comet",  "☄  Kometen",                "Leuchtende Lichtspuren über den Hintergrund"),
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
            if self._progress_job:
                try:
                    self.after_cancel(self._progress_job)
                except Exception:
                    pass
                self._progress_job = None
            self._progress_value = 0.0
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
            self._animate_progress(n / total)

        def _animate_progress(self, target):
            if self._progress_job:
                try:
                    self.after_cancel(self._progress_job)
                except Exception:
                    pass
                self._progress_job = None
            start = self._progress_value
            frames = 8

            def step(frame=1):
                try:
                    if not self.progress.winfo_exists():
                        self._progress_job = None
                        return
                    value = start + (target - start) * (frame / frames)
                    self.progress.set(value)
                    self._progress_value = value
                except Exception:
                    self._progress_job = None
                    return
                if frame < frames:
                    self._progress_job = self.after(16, lambda: step(frame + 1))
                else:
                    self._progress_job = None

            step()

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
