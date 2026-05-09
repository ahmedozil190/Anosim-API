import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import BOT_TOKEN, ANOSIM_API_KEY
from services.anosim_api import AnosimAPI
from services.account_creator import AccountCreator
from utils.strings import get_string
import database

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
api = AnosimAPI(ANOSIM_API_KEY)
creator = AccountCreator(ANOSIM_API_KEY)

# ─────────────────────────────────────────────
# /start
# ─────────────────────────────────────────────
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    builder = InlineKeyboardBuilder()
    builder.button(text="🛒 شراء حساب", callback_data="start_reg")
    builder.button(text="📊 حساباتي", callback_data="my_accounts")
    builder.button(text="💰 الرصيد", callback_data="balance")
    builder.button(text="📦 المخزون", callback_data="stock")
    builder.adjust(2)
    await message.answer(get_string('start'), reply_markup=builder.as_markup())

# ─────────────────────────────────────────────
# /balance
# ─────────────────────────────────────────────
@dp.message(Command("balance"))
@dp.callback_query(F.data == "balance")
async def cmd_balance(event):
    msg = event if isinstance(event, types.Message) else event.message
    try:
        balance = await api.get_balance()
        await msg.answer(get_string('balance', balance=balance))
    except Exception as e:
        await msg.answer(get_string('balance_error'))
        logger.error(f"Balance error: {e}")

# ─────────────────────────────────────────────
# /buy → Start registration flow
# ─────────────────────────────────────────────
@dp.message(Command("buy"))
@dp.callback_query(F.data == "start_reg")
async def start_reg_flow(event):
    msg = event if isinstance(event, types.Message) else event.message
    countries = await api.get_countries()
    if not countries:
        await msg.answer("❌ فشل في جلب قائمة الدول.")
        return

    builder = InlineKeyboardBuilder()
    for c in countries[:20]:
        builder.button(
            text=f"🌍 {c['name']} (${c.get('minPrice', '?')})",
            callback_data=f"country_{c['id']}"
        )
    builder.adjust(2)
    await msg.answer(get_string('choose_country'), reply_markup=builder.as_markup())

# ─────────────────────────────────────────────
# Country Selected → Start Automated Purchase
# ─────────────────────────────────────────────
@dp.callback_query(F.data.startswith("country_"))
async def select_country(callback: types.CallbackQuery):
    country_id = callback.data.split("_")[1]
    products = await api.get_products(country_id)
    telegram_product = next(
        (p for p in products if "telegram" in p.get('name', '').lower()), None
    )

    if not telegram_product:
        await callback.message.answer("❌ خدمة تيليجرام غير متوفرة لهذه الدولة.")
        return

    status_msg = await callback.message.answer(get_string('creating_acc'))

    async def update_status(status_type, **kwargs):
        templates = {
            'status_bought': get_string('status_bought', **kwargs),
            'status_requesting': get_string('status_requesting', **kwargs),
            'status_email_created': get_string('status_email_created', **kwargs),
            'status_email_success': get_string('status_email_success', **kwargs),
            'status_waiting': get_string('status_waiting', **kwargs),
        }
        text = templates.get(status_type)
        if text:
            try:
                await status_msg.edit_text(text)
            except Exception:
                pass

    result = await creator.create_account(
        country_id=country_id,
        product_id=telegram_product['id'],
        first_name="Ano",
        last_name="Sim",
        status_callback=update_status
    )

    if result['success']:
        await status_msg.edit_text(
            get_string('acc_success',
                       phone=result['phone'],
                       first_name=result['first_name'],
                       session=result['phone'])
        )
    else:
        await status_msg.edit_text(get_string('acc_failed', error=result['error']))

# ─────────────────────────────────────────────
# /stock → Show saved accounts
# ─────────────────────────────────────────────
@dp.message(Command("stock"))
@dp.callback_query(F.data == "stock")
async def cmd_stock(event):
    msg = event if isinstance(event, types.Message) else event.message
    accounts = database.get_all_accounts()
    if not accounts:
        await msg.answer(get_string('empty_stock'))
        return

    text = get_string('stock_list')
    for acc in accounts:
        text += f"📱 `{acc['phone_number']}` | 👤 {acc['first_name']} {acc['last_name']}\n"
    await msg.answer(text)

# ─────────────────────────────────────────────
# My Accounts (callback)
# ─────────────────────────────────────────────
@dp.callback_query(F.data == "my_accounts")
async def show_accounts(callback: types.CallbackQuery):
    await cmd_stock(callback)

# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────
async def main():
    database.init_db()
    os.makedirs("sessions", exist_ok=True)
    logger.info("Starting bot...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
