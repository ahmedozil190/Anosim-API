import asyncio
import logging
import os
import re
from telethon import TelegramClient, functions, types
from telethon.errors import SessionPasswordNeededError
from services.anosim_api import AnosimAPI
from services.email_service import EmailService
from config import TELEGRAM_API_ID, TELEGRAM_API_HASH, SESSIONS_DIR
import database

logger = logging.getLogger(__name__)

# --- ROBUST COMPATIBILITY HELPERS ---
def serialize_tg_string(s):
    b = s.encode('utf-8') if isinstance(s, str) else s
    if len(b) <= 253: res = bytes([len(b)]) + b
    else: res = b'\xfe' + len(b).to_bytes(3, 'little') + b
    return res + b'\x00' * (-(len(res)) % 4)

class EmailVerifyPurposeRegistration(types.TLObject):
    CONSTRUCTOR_ID = 0xb9d37505
    def _bytes(self): return b'\x05u\xd3\xb9'

class EmailVerifyPurposeLogin(types.TLObject):
    CONSTRUCTOR_ID = 0x43458af4
    def __init__(self, phone_number, phone_code_hash):
        self.phone_number, self.phone_code_hash = phone_number, phone_code_hash
    def _bytes(self):
        return b'\xf4\x8aEC' + serialize_tg_string(self.phone_number) + serialize_tg_string(self.phone_code_hash)

class AccountCreator:
    def __init__(self, api_key):
        self.api = AnosimAPI(api_key)
        self.email_service = EmailService()

    async def start_purchase(self, product_id, provider_id=0):
        order = await self.api.create_order(product_id, provider_id=provider_id)
        bookings = order.get("orderBookings") or order.get("bookings")
        if not order or not bookings: return None, "Order failed"
        phone, bid = bookings[0]['number'], bookings[0]['id']
        session_path = os.path.join(SESSIONS_DIR, f"{phone}")
        client = TelegramClient(session_path, TELEGRAM_API_ID, TELEGRAM_API_HASH, device_model='Samsung S23 Ultra', system_version='14', app_version='10.5.0')
        await client.connect()
        return {"client": client, "phone": phone, "id": bid}, None

    async def request_code(self, client, phone):
        try:
            sent_code = await asyncio.wait_for(client.send_code_request(phone), timeout=45)
            needs_email = type(sent_code.type).__name__ in ['SentCodeTypeEmail', 'SentCodeTypeApp']
            return sent_code, needs_email, None
        except Exception as e:
            if "email" in str(e).lower(): return None, True, None
            return None, False, str(e)

    async def send_email_code(self, client, email, phone, sent_code=None):
        """Ultra-resilient email code request for hosting environments."""
        try:
            # 1. Try to find official types first
            purpose = None
            is_app = sent_code and type(sent_code.type).__name__ == 'SentCodeTypeApp'
            
            try:
                # Search in all common namespaces
                from telethon.tl.types import auth, account
                reg_type = getattr(auth, 'EmailVerifyPurposeRegistration', getattr(account, 'EmailVerifyPurposeRegistration', None))
                log_type = getattr(auth, 'EmailVerifyPurposeLogin', getattr(account, 'EmailVerifyPurposeLogin', None))
                
                if is_app and sent_code and log_type:
                    purpose = log_type(phone_number=phone, phone_code_hash=sent_code.phone_code_hash)
                elif not is_app and reg_type:
                    purpose = reg_type()
            except: pass

            # 2. Fallback to manual robust classes if not found or failed
            if not purpose:
                if is_app and sent_code:
                    purpose = EmailVerifyPurposeLogin(phone, sent_code.phone_code_hash)
                else:
                    purpose = EmailVerifyPurposeRegistration()

            await client(functions.account.SendVerifyEmailCodeRequest(purpose=purpose, email=email))
            return None
        except Exception as e:
            logger.error(f"Hosting Email Fix Failed: {e}")
            return f"Email Request Failed: {e}"

    async def verify_email_and_poll(self, client, email, code, phone):
        try:
            await client(functions.account.VerifyEmailRequest(email=email, code=code))
            sent_code = await client.send_code_request(phone)
            return sent_code, None
        except Exception as e: return None, str(e)

    async def create_account_simple(self, client, phone, code, first_name="Ano", last_name="Sim"):
        try:
            await client.sign_up(code, first_name, last_name)
            return True, None
        except:
            try:
                await client.sign_in(phone, code)
                return True, None
            except Exception as e: return False, str(e)

    async def bypass_to_sms(self, client, phone, sent_code):
        try:
            await asyncio.sleep(65)
            sent_code = await client(functions.auth.ResendCodeRequest(phone_number=phone, phone_code_hash=sent_code.phone_code_hash))
            return sent_code, None
        except Exception as e: return None, str(e)
