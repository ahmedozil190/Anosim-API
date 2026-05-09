import logging
import asyncio
import re
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

from config import BOT_TOKEN, ANOSIM_API_KEY
from services.anosim_api import AnosimAPI
from services.account_creator import AccountCreator
import database
from utils.strings import get_string

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize bot and dispatcher
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
anosim = AnosimAPI(ANOSIM_API_KEY)
creator = AccountCreator(ANOSIM_API_KEY)

# --- States for Interactive Step-by-Step ---
class RegisterStates(StatesGroup):
    waiting_for_email = State()
    waiting_for_email_code = State()

# Active sessions store
active_sessions = {}

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    lang = database.get_user_language(message.from_user.id)
    await message.answer(get_string('start', lang))

@dp.message(Command("lang"))
async def cmd_lang(message: types.Message):
    lang = database.get_user_language(message.from_user.id)
    builder = InlineKeyboardBuilder()
    builder.button(text="العربية 🇸🇦", callback_data="setlang_ar")
    builder.button(text="English 🇺🇸", callback_data="setlang_en")
    builder.adjust(2)
    await message.answer(get_string('choose_lang', lang), reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("setlang_"))
async def process_setlang(callback: types.CallbackQuery):
    lang = callback.data.split("_")[1]
    database.set_user_language(callback.from_user.id, lang)
    await callback.answer(get_string('lang_updated', lang))
    await callback.message.edit_text(get_string('start', lang))

@dp.message(Command("buy", "test"))
async def cmd_buy(message: types.Message):
    lang = database.get_user_language(message.from_user.id)
    countries = await anosim.get_countries()
    if not countries:
        await message.answer(get_string('countries_error', lang))
        return
    builder = InlineKeyboardBuilder()
    for country in countries[:15]:
        builder.button(text=country['country'], callback_data=f"buy_{country['id']}")
    builder.adjust(2)
    await message.answer(get_string('choose_country', lang), reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("buy_"))
async def process_buy_confirm(callback: types.CallbackQuery):
    lang = database.get_user_language(callback.from_user.id)
    country_id = int(callback.data.split("_")[1])
    products = await anosim.get_products(country_id)
    tg = next((p for p in products if "Telegram" in p.get("service", "")), None)
    if not tg:
        await callback.answer("Service not available", show_alert=True)
        return
    product = await anosim.get_product_details(tg['id'])
    providers = product.get("provider", [])
    builder = InlineKeyboardBuilder()
    for p in [p for p in providers if p['availableCount'] > 0]:
        builder.button(text=f"{p['name']} ({p['availableCount']})", callback_data=f"conf_{country_id}_{product['id']}_{p['id']}")
    builder.button(text=get_string('cancel_btn', lang), callback_data="cancel_order")
    builder.adjust(1)
    await callback.message.edit_text(get_string('confirm_purchase', lang, country=product['country'], price=product['price'], count=0, provider="Any"), reply_markup=builder.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("conf_"))
async def process_buy_final(callback: types.CallbackQuery, state: FSMContext):
    lang = database.get_user_language(callback.from_user.id)
    _, country_id, product_id, provider_id = callback.data.split("_")
    
    await callback.message.edit_text("⏳ Buying number...")
    data, error = await creator.start_purchase(int(product_id), int(provider_id))
    if error:
        await callback.message.answer(f"❌ Error: {error}")
        return

    active_sessions[callback.from_user.id] = data
    await callback.message.answer(f"✅ Number: `{data['phone']}`\n📲 Requesting code...")
    
    sent_code, needs_email, error = await creator.request_code(data['client'], data['phone'])
    if error:
        await callback.message.answer(f"❌ Telegram Error: {error}")
        return

    if needs_email:
        await callback.message.answer("📧 Telegram is asking for an Email.\n\n👉 Please **SEND** the email address you want to use:")
        await state.update_data(sent_code=sent_code)
        await state.set_state(RegisterStates.waiting_for_email)
    else:
        await callback.message.answer("📩 Code requested! Waiting for SMS...")
        asyncio.create_task(poll_sms(callback.message, data))

@dp.message(RegisterStates.waiting_for_email)
async def process_email(message: types.Message, state: FSMContext):
    email = message.text.strip()
    data = active_sessions.get(message.from_user.id)
    if not data:
        await message.answer("❌ Session lost. Start again.")
        await state.clear()
        return

    s_data = await state.get_data()
    await message.answer(f"⏳ Sending verification to `{email}`...")
    error = await creator.send_email_code(data['client'], email, data['phone'], s_data.get('sent_code'))
    
    if error:
        if "Email flow failed" in error:
            await message.answer("⚠️ Email flow failed. Switching to SMS bypass... Please wait **65 seconds**...")
            sent_code, bypass_error = await creator.bypass_to_sms(data['client'], data['phone'], s_data.get('sent_code'))
            if bypass_error:
                await message.answer(f"❌ Bypass failed: {bypass_error}")
                return
            await message.answer("✅ Bypass successful! Now waiting for SMS from Anosim...")
            await state.clear()
            asyncio.create_task(poll_sms(message, data))
            return
        else:
            await message.answer(f"❌ Error: {error}")
            return

    await state.update_data(email=email)
    await message.answer("📩 Code sent! Please **SEND** the code from your email:")
    await state.set_state(RegisterStates.waiting_for_email_code)

@dp.message(RegisterStates.waiting_for_email_code)
async def process_email_code(message: types.Message, state: FSMContext):
    code = message.text.strip()
    data = active_sessions.get(message.from_user.id)
    if not data: return
    
    s_data = await state.get_data()
    email = s_data.get('email', '')
    
    await message.answer("⏳ Verifying email code...")
    sent_code, error = await creator.verify_email_and_poll(data['client'], email, code, data['phone'])
    
    if error:
        await message.answer(f"❌ Error: {error}")
        return

    await message.answer("✅ Email Verified! Now waiting for SMS code...")
    await state.clear()
    asyncio.create_task(poll_sms(message, data))

async def poll_sms(message, data):
    phone, bid, client = data['phone'], data['id'], data['client']
    code = None
    for attempt in range(1, 21):
        sms_list = await anosim.get_sms(bid)
        if sms_list:
            for sms in sms_list:
                match = re.search(r'\b(\d{5})\b', sms['messageText'])
                if match: code = match.group(1); break
        if code: break
        await asyncio.sleep(15)
            
    if code:
        await message.answer(f"🎉 SMS Code: `{code}`. Finalizing...")
        success, error = await creator.create_account_simple(client, phone, code)
        if success:
            database.add_account(phone, phone, "ID", "HASH", "Ano", "Sim")
            await message.answer(f"✅ Account Created! Phone: `{phone}`")
        else:
            await message.answer(f"❌ Final Auth Failed: {error}")
    else:
        await message.answer("❌ SMS Timeout.")
        await anosim.cancel_order_booking(bid)
    
    await client.disconnect()
    if message.from_user.id in active_sessions: del active_sessions[message.from_user.id]

@dp.callback_query(F.data == "cancel_order")
async def process_cancel(callback: types.CallbackQuery):
    await callback.message.edit_text("Order cancelled.")

async def main():
    database.init_db()
    logger.info("Starting bot...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try: asyncio.run(main())
    except (KeyboardInterrupt, SystemExit): logger.info("Bot stopped.")
