import asyncio
import logging
import os
import re
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import BOT_TOKEN, ANOSIM_API_KEY
from services.anosim_api import AnosimAPI
from services.account_creator import AccountCreator
from utils.strings import STRINGS, get_string
import database

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
api = AnosimAPI(ANOSIM_API_KEY)
creator = AccountCreator(ANOSIM_API_KEY)

class RegisterStates(StatesGroup):
    waiting_for_country = State()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    database.init_db()
    builder = InlineKeyboardBuilder()
    builder.button(text="🌍 Start Registration", callback_data="start_reg")
    builder.button(text="📊 My Accounts", callback_data="my_accounts")
    await message.answer(get_string('start'), reply_markup=builder.as_markup())

@dp.callback_query(F.data == "start_reg")
async def start_reg_flow(callback: types.CallbackQuery):
    countries = await api.get_countries()
    if not countries:
        await callback.message.answer("❌ Error: Could not fetch countries.")
        return
    
    builder = InlineKeyboardBuilder()
    for c in countries[:20]:  # Top 20 countries
        builder.button(text=f"{c['name']} (${c['minPrice']})", callback_data=f"country_{c['id']}")
    builder.adjust(2)
    await callback.message.answer("📍 Select a Country:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("country_"))
async def select_service(callback: types.CallbackQuery):
    country_id = callback.data.split("_")[1]
    products = await api.get_products(country_id)
    telegram_product = next((p for p in products if "telegram" in p['name'].lower()), None)
    
    if not telegram_product:
        await callback.message.answer("❌ Error: Telegram service not available for this country.")
        return

    # Trigger FULLY AUTOMATED flow
    status_msg = await callback.message.answer("🔄 **Starting Automated Registration...**\n- Buying number...")
    
    async def update_status(status_type, **kwargs):
        if status_type == 'status_bought':
            await status_msg.edit_text(f"✅ **Number Bought:** `{kwargs['phone']}`\n- ID: `{kwargs['id']}`\n- Requesting code...")
        elif status_type == 'status_requesting':
            await status_msg.edit_text(f"📲 **Requesting SMS Code...**\n- Number: `{kwargs['phone']}`")
        elif status_type == 'status_waiting':
            await status_msg.edit_text(f"⏳ **Waiting for Code...**\n- Attempt: `{kwargs['attempt']}/{kwargs['total']}`\n- Please wait...")

    result = await creator.create_account(
        country_id=country_id,
        product_id=telegram_product['id'],
        first_name="Ano",
        last_name="Sim",
        status_callback=update_status
    )

    if result['success']:
        await status_msg.edit_text(f"🎉 **Registration Successful!**\n\n- Phone: `{result['phone']}`\n- Name: `{result['first_name']}`\n- The session file is saved in the server.")
    else:
        await status_msg.edit_text(f"❌ **Registration Failed:**\n`{result['error']}`")

@dp.callback_query(F.data == "my_accounts")
async def show_accounts(callback: types.CallbackQuery):
    accounts = database.get_all_accounts()
    if not accounts:
        await callback.message.answer("📭 No accounts registered yet.")
        return
    
    msg = "📊 **Your Registered Accounts:**\n\n"
    for acc in accounts:
        msg += f"📱 `{acc[1]}` | 👤 {acc[5]} {acc[6]}\n"
    await callback.message.answer(msg)

async def main():
    database.init_db()
    if not os.path.exists('sessions'): os.makedirs('sessions')
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
