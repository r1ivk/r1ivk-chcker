import asyncio
import logging
import sqlite3
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

# --- توكن البوت الخاص بك ---
API_TOKEN = "8948074959:AAGIqYYLk0UeD7KUmWbRKqgdYs1n44dRjmo"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()


# --- قاعدة البيانات ---
def init_db():
  conn = sqlite3.connect("store_bot.db")
  cursor = conn.cursor()

  # جدول المستخدمين
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            points INTEGER DEFAULT 0,
            referred_by INTEGER,
            lang TEXT DEFAULT 'ar'
        )
    """)

  # جدول الحسابات (اليوزر والباسورد منفصلين لسهولة النسخ)
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            password TEXT,
            category TEXT
        )
    """)

  # جدول المشتريات (لحفظ الحسابات التي اشتراها المستخدم للوصول إليها لاحقاً بلا حدود)
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS purchases (
            user_id INTEGER,
            account_id INTEGER,
            PRIMARY KEY (user_id, account_id)
        )
    """)

  conn.commit()
  conn.close()


init_db()

# --- النصوص والترجمات ---
texts = {
    "ar": {
        "welcome": (
            "أهلاً بك في متجر r1ivk Store 🎮\nاختر لغتك المفضلة أو استعرض"
            " الأقسام الجديدة من القائمة أدناه 👇."
        ),
        "lang_changed": "تم تغيير اللغة إلى العربية بنجاح! 🇸🇦",
        "btn_ref": "💎 تجميع رصيد (رابط الدعوة)",
        "btn_info": "👤 معلومات حسابك",
        "btn_redeem": "🎁 استبدال النقاط (سحب حساب)",
        "btn_my_purchases": "📁 حساباتي المشراة",
        "btn_lang": "🌐 تغيير اللغة / Change Language",
        "account_info": (
            "👤 **معلومات حسابك:**\n\n🆔 رقم المستخدم:"
            " `{}`\n💎 النقاط: `{}` نقطة\n\n🔗 رابط الدعوة الخاص بك (أرسله"
            " لأصدقائك):\n`{}`\n*(ستحصل على **1 نقطة** مقابل كل شخص يدخل من"
            " رابطك!)*"
        ),
        "redeem_title": (
            "🎁 **قسم استبدال الحسابات (مرتب وواضح):**\n\nاختر نوع الحساب الذي"
            " تريد استبداله بنقاطك:"
        ),
        "my_purchases_title": (
            "📁 **حساباتك المشراة (متاحة لك للأبد):**\n\nاضغط على الحساب لعرض"
            " بياناته متى شئت بدون خصم أي نقاط:"
        ),
        "no_purchases": "❌ لم تقم بشراء أي حسابات حتى الآن.",
        "no_accounts": (
            "❌ عذراً، لا توجد حسابات متاحة حالياً في هذا القسم. تابع التجميع لحين"
            " وصول دفعة جديدة!"
        ),
        "not_enough_points": (
            "⚠️ نقاطك غير كافية! يلزمك المزيد من النقاط لفتح هذا الحساب."
        ),
        "success_redeem": (
            "🎉 **مبروك! تم شراء الحساب بنجاح:**\n\n👤 **اسم المستخدم (Username):**"
            " `{}`\n🔑 **كلمة المرور (Password):**\n`{}`\n\n*(تم حفظ الحساب في"
            " سجلك للأبد)*"
        ),
        "success_reaccess": (
            "🔓 **إليك بيانات الحساب (مشتري مسبقاً):**\n\n👤 **اسم المستخدم"
            " (Username):** `{}`\n🔑 **كلمة المرور (Password):**\n`{}`"
        ),
        "btn_back": "⬅️ رجوع للقائمة الرئيسية",
    },
    "en": {
        "welcome": (
            "Welcome to r1ivk Store 🎮\nChoose your preferred language or"
            " explore the updated game sections below 👇."
        ),
        "lang_changed": "Language changed to English successfully! 🇬🇧",
        "btn_ref": "💎 Earn Points (Ref Link)",
        "btn_info": "👤 Account Info",
        "btn_redeem": "🎁 Redeem Points",
        "btn_my_purchases": "📁 My Purchased Accounts",
        "btn_lang": "🌐 تغيير اللغة / Change Language",
        "account_info": (
            "👤 **Account Info:**\n\n🆔 User ID: `{}`\n💎 Points: `{}`"
            " pts\n\n🔗 Your Referral Link (Share with friends):\n`{}`\n*(You will"
            " get **1 point** for every person who joins via your link!)*"
        ),
        "redeem_title": (
            "🎁 **Accounts Redemption Section:**\n\nChoose the account category"
            " you want to redeem:"
        ),
        "my_purchases_title": (
            "📁 **Your Purchased Accounts (Yours Forever):**\n\nClick on any"
            " account to view its details anytime for free:"
        ),
        "no_purchases": "❌ You haven't purchased any accounts yet.",
        "no_accounts": (
            "❌ Sorry, no accounts are currently available in this category."
            " Keep earning points!"
        ),
        "not_enough_points": (
            "⚠️ Not enough points! You need more points to redeem this account."
        ),
        "success_redeem": (
            "🎉 **Congratulations! Account purchased successfully:**\n\n👤"
            " **Username:** `{}`\n🔑 **Password:**\n`{}`\n\n*(Saved to your"
            " profile forever)*"
        ),
        "success_reaccess": (
            "🔓 **Account details (Previously purchased):**\n\n👤"
            " **Username:** `{}`\n🔑 **Password:**\n`{}`"
        ),
        "btn_back": "Main Menu",
    },
}


def get_lang(user_id):
  conn = sqlite3.connect("store_bot.db")
  cursor = conn.cursor()
  cursor.execute("SELECT lang FROM users WHERE user_id = ?", (user_id,))
  row = cursor.fetchone()
  conn.close()
  return row[0] if row else "ar"


def get_main_keyboard(lang):
  t = texts[lang]
  builder = InlineKeyboardBuilder()
  builder.row(
      InlineKeyboardButton(text=t["btn_ref"], callback_data="earn_points")
  )
  builder.row(
      InlineKeyboardButton(text=t["btn_info"], callback_data="account_info")
  )
  builder.row(
      InlineKeyboardButton(text=t["btn_redeem"], callback_data="redeem_menu")
  )
  builder.row(
      InlineKeyboardButton(
          text=t["btn_my_purchases"], callback_data="my_purchases"
      )
  )
  builder.row(
      InlineKeyboardButton(text=t["btn_lang"], callback_data="toggle_lang")
  )
  return builder.as_markup()


@dp.message(CommandStart())
async def cmd_start(message: types.Message):
  user_id = message.from_user.id
  args = message.text.split()

  conn = sqlite3.connect("store_bot.db")
  cursor = conn.cursor()
  cursor.execute("SELECT lang, points FROM users WHERE user_id = ?", (user_id,))
  user = cursor.fetchone()

  if not user:
    referred_by = None
    if len(args) > 1 and args[1].isdigit():
      ref_id = int(args[1])
      if ref_id != user_id:
        cursor.execute(
            "SELECT user_id FROM users WHERE user_id = ?", (ref_id,)
        )
        if cursor.fetchone():
          referred_by = ref_id
          cursor.execute(
              "UPDATE users SET points = points + 1 WHERE user_id = ?", (ref_id,)
          )

    cursor.execute(
        "INSERT INTO users (user_id, points, referred_by, lang) VALUES (?, 0,"
        " ?, 'ar')",
        (user_id, referred_by),
    )
    conn.commit()
    lang = "ar"
  else:
    lang = user[0]
  conn.close()

  t = texts[lang]
  await message.answer(t["welcome"], reply_markup=get_main_keyboard(lang))


@dp.callback_query(F.data == "toggle_lang")
async def toggle_lang(callback: types.CallbackQuery):
  user_id = callback.from_user.id
  current_lang = get_lang(user_id)
  new_lang = "en" if current_lang == "ar" else "ar"

  conn = sqlite3.connect("store_bot.db")
  cursor = conn.cursor()
  cursor.execute(
      "UPDATE users SET lang = ? WHERE user_id = ?", (new_lang, user_id)
  )
  conn.commit()
  conn.close()

  t = texts[new_lang]
  await callback.message.edit_text(
      t["lang_changed"], reply_markup=get_main_keyboard(new_lang)
  )
  await callback.answer()


@dp.callback_query(F.data == "account_info")
async def show_account_info(callback: types.CallbackQuery):
  user_id = callback.from_user.id
  lang = get_lang(user_id)

  conn = sqlite3.connect("store_bot.db")
  cursor = conn.cursor()
  cursor.execute("SELECT points FROM users WHERE user_id = ?", (user_id,))
  points = cursor.fetchone()[0]
  conn.close()

  bot_info = await bot.get_me()
  ref_link = f"https://t.me/{bot_info.username}?start={user_id}"

  t = texts[lang]
  text = t["account_info"].format(user_id, points, ref_link)

  builder = InlineKeyboardBuilder()
  builder.row(
      InlineKeyboardButton(text=t["btn_back"], callback_data="main_menu")
  )

  await callback.message.edit_text(
      text, reply_markup=builder.as_markup(), disable_web_page_preview=True
  )
  await callback.answer()


@dp.callback_query(F.data == "earn_points")
async def earn_points_menu(callback: types.CallbackQuery):
  user_id = callback.from_user.id
  lang = get_lang(user_id)
  bot_info = await bot.get_me()
  ref_link = f"https://t.me/{bot_info.username}?start={user_id}"

  if lang == "ar":
    text = (
        "💎 **طريقة تجميع النقاط (دعوة الأصدقاء):**\n\nقم بنسخ رابط الدعوة الخاص"
        " بك وأرسله لأصدقائك.\nلكل شخص يدخل البوت عبر رابطك الخاص، ستحصل أنت"
        " على **1 نقطة** فوراً!\n\n🔗 رابطك الخاص:\n`{}`".format(ref_link)
    )
  else:
    text = (
        "💎 **How to earn points (Invite Friends):**\n\nCopy your referral link"
        " and share it with friends.\nFor every person who joins via your"
        " link, you will get **1 point** instantly!\n\n🔗 Your"
        " link:\n`{}`".format(ref_link)
    )

  builder = InlineKeyboardBuilder()
  builder.row(
      InlineKeyboardButton(
          text=texts[lang]["btn_back"], callback_data="main_menu"
      )
  )

  await callback.message.edit_text(
      text, reply_markup=builder.as_markup(), disable_web_page_preview=True
  )
  await callback.answer()


@dp.callback_query(F.data == "redeem_menu")
async def redeem_menu(callback: types.CallbackQuery):
  user_id = callback.from_user.id
  lang = get_lang(user_id)
  t = texts[lang]

  builder = InlineKeyboardBuilder()
  builder.row(
      InlineKeyboardButton(
          text="🔥 Resident Evil 4 Remake + 30 AAA Games (30 pts)",
          callback_data="redeem_re4remake",
      )
  )
  builder.row(
      InlineKeyboardButton(
          text="🪓 God of War (2018) + Ragnarok (20 pts)",
          callback_data="redeem_godofwar",
      )
  )
  builder.row(
      InlineKeyboardButton(
          text="🤖 Cyberpunk 2077 (20 pts)", callback_data="redeem_cyberpunk"
      )
  )
  builder.row(
      InlineKeyboardButton(
          text="🧟 Resident Evil Requiem (15 pts)",
          callback_data="redeem_requiem",
      )
  )
  builder.row(
      InlineKeyboardButton(
          text="🤠 Red Dead Redemption 2 (10 pts)", callback_data="redeem_rdr2"
      )
  )
  builder.row(
      InlineKeyboardButton(
          text="⚽ FC 26 / FIFA 26 (10 pts)", callback_data="redeem_fifa26"
      )
  )
  builder.row(
      InlineKeyboardButton(
          text="🌿 The Last of Us Part I & II (10 pts)",
          callback_data="redeem_thelastofus",
      )
  )
  builder.row(
      InlineKeyboardButton(
          text="🕷️ Spider-Man Remastered (10 pts)",
          callback_data="redeem_spiderman1",
      )
  )
  builder.row(
      InlineKeyboardButton(
          text="🕷️ Spider-Man: Miles Morales (10 pts)",
          callback_data="redeem_miles",
      )
  )
  builder.row(
      InlineKeyboardButton(
          text="🕷️ Spider-Man 2 (10 pts)", callback_data="redeem_spiderman2"
      )
  )
  builder.row(
      InlineKeyboardButton(
          text="🏎️ Forza Horizon 6 (10 pts)", callback_data="redeem_forza"
      )
  )
  builder.row(
      InlineKeyboardButton(
          text="🗡️ Ghost of Tsushima (Gold Edition) (10 pts)",
          callback_data="redeem_tsushima",
      )
  )
  builder.row(
      InlineKeyboardButton(
          text="🦇 Batman Arkham Trilogy (10 pts)",
          callback_data="redeem_batman",
      )
  )
  builder.row(
      InlineKeyboardButton(
          text="🌀 Naruto Shippuden: Ultimate Ninja Storm (10 pts)",
          callback_data="redeem_naruto",
      )
  )
  builder.row(
      InlineKeyboardButton(
          text="🐀 A Plague Tale: Innocence (Part 1) (10 pts)",
          callback_data="redeem_plague1",
      )
  )
  builder.row(
      InlineKeyboardButton(
          text="🐀 A Plague Tale: Requiem (Part 2) (10 pts)",
          callback_data="redeem_plague2",
      )
  )
  builder.row(
      InlineKeyboardButton(
          text="🏎️ GTA V Account (8 pts)", callback_data="redeem_gta"
      )
  )
  builder.row(
      InlineKeyboardButton(
          text="💻 Watch Dogs (5 pts)", callback_data="redeem_watchdogs"
      )
  )
  builder.row(
      InlineKeyboardButton(
          text="🍿 Netflix Account (3 pts)", callback_data="redeem_netflix"
      )
  )
  builder.row(
      InlineKeyboardButton(
          text="🎮 حساب ستيم عشوائي (2 pts)", callback_data="redeem_steam"
      )
  )
  builder.row(
      InlineKeyboardButton(text=t["btn_back"], callback_data="main_menu")
  )

  await callback.message.edit_text(
      t["redeem_title"], reply_markup=builder.as_markup()
  )
  await callback.answer()


@dp.callback_query(F.data == "my_purchases")
async def my_purchases_menu(callback: types.CallbackQuery):
  user_id = callback.from_user.id
  lang = get_lang(user_id)
  t = texts[lang]

  conn = sqlite3.connect("store_bot.db")
  cursor = conn.cursor()
  cursor.execute(
      """
        SELECT accounts.id, accounts.category 
        FROM purchases 
        JOIN accounts ON purchases.account_id = accounts.id 
        WHERE purchases.user_id = ?
    """,
      (user_id,),
  )
  purchased_accounts = cursor.fetchall()
  conn.close()

  builder = InlineKeyboardBuilder()

  if not purchased_accounts:
    builder.row(
        InlineKeyboardButton(text=t["btn_back"], callback_data="main_menu")
    )
    await callback.message.edit_text(
        f"{t['my_purchases_title']}\n\n{t['no_purchases']}",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()
    return

  for acc_id, category in purchased_accounts:
    builder.row(
        InlineKeyboardButton(
            text=f"📦 حساب: {category}",
            callback_data=f"show_my_acc_{acc_id}",
        )
    )

  builder.row(
      InlineKeyboardButton(text=t["btn_back"], callback_data="main_menu")
  )
  await callback.message.edit_text(
      t["my_purchases_title"], reply_markup=builder.as_markup()
  )
  await callback.answer()


@dp.callback_query(F.data.startswith("show_my_acc_"))
async def show_my_account(callback: types.CallbackQuery):
  user_id = callback.from_user.id
  lang = get_lang(user_id)
  t = texts[lang]

  acc_id = int(callback.data.split("_")[3])

  conn = sqlite3.connect("store_bot.db")
  cursor = conn.cursor()
  cursor.execute(
      """
        SELECT accounts.username, accounts.password 
        FROM purchases 
        JOIN accounts ON purchases.account_id = accounts.id 
        WHERE purchases.user_id = ? AND purchases.account_id = ?
    """,
      (user_id, acc_id),
  )
  acc = cursor.fetchone()
  conn.close()

  builder = InlineKeyboardBuilder()
  builder.row(
      InlineKeyboardButton(text=t["btn_back"], callback_data="my_purchases")
  )

  if not acc:
    await callback.answer(
        "❌ عذراً، هذا الحساب غير موجود في سجلك.", show_alert=True
    )
    return

  username, password = acc
  await callback.message.edit_text(
      t["success_reaccess"].format(username, password),
      reply_markup=builder.as_markup(),
  )
  await callback.answer()


@dp.callback_query(F.data.startswith("redeem_"))
async def process_redeem(callback: types.CallbackQuery):
  user_id = callback.from_user.id
  lang = get_lang(user_id)
  t = texts[lang]

  category = callback.data.split("_", 1)[1]

  if category == "re4remake":
    cost = 30
  elif category in ["godofwar", "cyberpunk"]:
    cost = 20
  elif category == "requiem":
    cost = 15
  elif category in [
      "rdr2",
      "fifa26",
      "thelastofus",
      "spiderman1",
      "miles",
      "spiderman2",
      "forza",
      "tsushima",
      "batman",
      "naruto",
      "plague1",
      "plague2",
  ]:
    cost = 10
  elif category == "gta":
    cost = 8
  elif category == "watchdogs":
    cost = 5
  elif category == "netflix":
    cost = 3
  else:
    cost = 2

  conn = sqlite3.connect("store_bot.db")
  cursor = conn.cursor()

  cursor.execute(
      "SELECT id, username, password FROM accounts WHERE category = ? LIMIT 1",
      (category,),
  )
  acc = cursor.fetchone()

  if not acc:
    await callback.answer(t["no_accounts"], show_alert=True)
    conn.close()
    return

  acc_id, username, password = acc

  cursor.execute(
      "SELECT 1 FROM purchases WHERE user_id = ? AND account_id = ?",
      (user_id, acc_id),
  )
  already_purchased = cursor.fetchone()

  if already_purchased:
    conn.close()
    await callback.message.edit_text(
        t["success_reaccess"].format(username, password),
        reply_markup=InlineKeyboardBuilder()
        .row(InlineKeyboardButton(text=t["btn_back"], callback_data="main_menu"))
        .as_markup(),
    )
    await callback.answer()
    return

  cursor.execute("SELECT points FROM users WHERE user_id = ?", (user_id,))
  user_points = cursor.fetchone()[0]

  if user_points < cost:
    await callback.answer(t["not_enough_points"], show_alert=True)
    conn.close()
    return

  cursor.execute(
      "UPDATE users SET points = points - ? WHERE user_id = ?", (cost, user_id)
  )
  cursor.execute(
      "INSERT OR IGNORE INTO purchases (user_id, account_id) VALUES (?, ?)",
      (user_id, acc_id),
  )
  conn.commit()
  conn.close()

  await callback.message.edit_text(
      t["success_redeem"].format(username, password),
      reply_markup=InlineKeyboardBuilder()
      .row(InlineKeyboardButton(text=t["btn_back"], callback_data="main_menu"))
      .as_markup(),
  )
  await callback.answer()


@dp.callback_query(F.data == "main_menu")
async def back_to_main(callback: types.CallbackQuery):
  user_id = callback.from_user.id
  lang = get_lang(user_id)
  t = texts[lang]
  await callback.message.edit_text(
      t["welcome"], reply_markup=get_main_keyboard(lang)
  )
  await callback.answer()


async def main():
  conn = sqlite3.connect("store_bot.db")
  cursor = conn.cursor()

  accounts_to_add = [
      (
          "re4remake",
          "pinokio542",
          "EYK2Y99Z2TK5",
      ),
      (
          "godofwar",
          "seekkeygow2018",
          "XUgStsAmHGUM",
      ),
      (
          "cyberpunk",
          "c21282",
          "asdAVXab21Z",
      ),
      (
          "requiem",
          "req_user_official_1984",
          "pass_req_secure_99",
      ),
      (
          "rdr2",
          "followinghoverfly3787",
          "f-r-e-e-akk-tg:@hyznet",
      ),
      (
          "fifa26",
          "svfwqhmr6zrth7rj",
          "Ivancito2009_",
      ),
      (
          "thelastofus",
          "thelast1q",
          "playerok.com/profile/QAVIX",
      ),
      (
          "spiderman1",
          "sp1_remastered_user",
          "pass_sp1_2026",
      ),
      (
          "miles",
          "miles_morales_pc_user",
          "pass_miles_01",
      ),
      (
          "spiderman2",
          "sp2_by_heero",
          "https://t.me/steamaccountsog",
      ),
      (
          "forza",
          "duhl15773",
          "Muhammadknio12!",
      ),
      (
          "tsushima",
          "MythicStore_GOT_01",
          "https://t.me/Steam_Family",
      ),
      (
          "batman",
          "batman_arkham_trilogy_user",
          "pass_arkham_123",
      ),
      (
          "naruto",
          "naruto_storm_series_pc",
          "pass_naruto_storm_99",
      ),
      (
          "plague1",
          "aplaguetale_innocence_pc",
          "pass_plague_innocence_1",
      ),
      (
          "plague2",
          "aplaguetale_requiem_pc",
          "pass_plague_requiem_2",
      ),
      (
          "gta",
          "hedpy459961",
          "gta_secure_pass_88",
      ),
      (
          "watchdogs",
          "jp30ekXr",
          "wa72ITSA",
      ),
      (
          "netflix",
          "netflix_premium_acc_01",
          "pass_net_789",
      ),
  ]

  for cat, user_val, pass_val in accounts_to_add:
    cursor.execute("SELECT COUNT(*) FROM accounts WHERE category = ?", (cat,))
    if cursor.fetchone()[0] == 0:
      cursor.execute(
          "INSERT INTO accounts (username, password, category) VALUES (?, ?,"
          " ?)",
          (user_val, pass_val, cat),
      )
      conn.commit()

  conn.close()
  await dp.start_polling(bot)


if __name__ == "__main__":
  asyncio.run(main())
