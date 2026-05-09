import asyncio
import logging
import os
import re
from telethon import TelegramClient, functions, types
from telethon.errors import SessionPasswordNeededError, RPCError
from services.anosim_api import AnosimAPI
from services.email_service import EmailService
from config import TELEGRAM_API_ID, TELEGRAM_API_HASH, SESSIONS_DIR
import database

logger = logging.getLogger(__name__)

# --- ROBUST TL FALLBACKS ---
class EmailVerifyPurposeRegistration(types.TLObject):
    CONSTRUCTOR_ID = 0xb9d37505
    def _bytes(self): return b'\x05u\xd3\xb9'

class EmailVerifyPurposeLogin(types.TLObject):
    CONSTRUCTOR_ID = 0x43458af4
    def __init__(self, phone, hash): self.phone, self.hash = phone, hash
    def _bytes(self):
        # Manual serialization for strings
        def s(txt):
            b = txt.encode('utf-8'); l = len(b)
            res = bytes([l]) + b if l <= 253 else b'\xfe' + l.to_bytes(3, 'little') + b
            return res + b'\x00' * (-(len(res)) % 4)
        return b'\xf4\x8aEC' + s(self.phone) + s(self.hash)

class AccountCreator:
    def __init__(self, api_key):
        self.api = AnosimAPI(api_key)
        self.email_service = EmailService()

    async def create_account(self, country_id, product_id, first_name, last_name, proxy=None, provider_id=0, status_callback=None):
        """Fully automated account creation flow."""
        # 1. Buy Number
        order = await self.api.create_order(product_id, provider_id=provider_id)
        bookings = order.get("orderBookings") or order.get("bookings")
        if not order or not bookings: return {"success": False, "error": "Order failed"}
        phone, bid = bookings[0]['number'], bookings[0]['id']
        
        if status_callback: await status_callback('status_bought', phone=phone, id=bid)

        # 2. Client Setup
        session_path = os.path.join(SESSIONS_DIR, f"{phone}")
        if os.path.exists(f"{session_path}.session"): os.remove(f"{session_path}.session")
        client = TelegramClient(session_path, TELEGRAM_API_ID, TELEGRAM_API_HASH, device_model='Android 13', system_version='13.0', app_version='10.1.1')
        
        success = False
        try:
            await client.connect()
            if status_callback: await status_callback('status_requesting', phone=phone, id=bid)
            
            # 3. Request Initial Code
            sent_code = await client.send_code_request(phone)
            needs_email = isinstance(sent_code.type, (types.auth.SentCodeTypeEmail, types.auth.SentCodeTypeApp))
            
            # 4. Handle Email Automatically
            if needs_email:
                if status_callback: await status_callback('status_waiting', phone=phone, id=bid, attempt="Creating Email", total="Auto")
                email = await self.email_service.create_account()
                if not email: return {"success": False, "error": "Failed to create temp email"}
                
                # Use robust fallback types for purpose
                is_app = isinstance(sent_code.type, types.auth.SentCodeTypeApp)
                purpose = EmailVerifyPurposeLogin(phone, sent_code.phone_code_hash) if is_app else EmailVerifyPurposeRegistration()
                
                try:
                    await client(functions.account.SendVerifyEmailCodeRequest(purpose=purpose, email=email))
                    if status_callback: await status_callback('status_waiting', phone=phone, id=bid, attempt="Email Sent", total="Waiting Code")
                    email_code = await self.email_service.wait_for_code(timeout=60)
                    if not email_code:
                        # If email fails, try bypass to SMS after 65s
                        await asyncio.sleep(65)
                        sent_code = await client(functions.auth.ResendCodeRequest(phone_number=phone, phone_code_hash=sent_code.phone_code_hash))
                    else:
                        await client(functions.account.VerifyEmailRequest(email=email, code=email_code))
                        await asyncio.sleep(1)
                        sent_code = await client.send_code_request(phone)
                except Exception as e:
                    logger.warning(f"Email flow failed ({e}), waiting for SMS bypass...")
                    await asyncio.sleep(65)
                    sent_code = await client(functions.auth.ResendCodeRequest(phone_number=phone, phone_code_hash=sent_code.phone_code_hash))

            # 5. Poll SMS from Anosim
            code = None
            for attempt in range(1, 21):
                if status_callback: await status_callback('status_waiting', phone=phone, id=bid, attempt=attempt, total=20)
                await asyncio.sleep(15)
                sms_list = await self.api.get_sms(bid)
                if sms_list:
                    for sms in sms_list:
                        match = re.search(r'\b(\d{5})\b', sms['messageText'])
                        if match: code = match.group(1); break
                if code: break
            
            if not code:
                await self.api.cancel_order_booking(bid)
                return {"success": False, "error": "SMS timeout"}

            # 6. Finalize Auth
            try:
                await client.sign_up(code, first_name, last_name)
            except:
                await client.sign_in(phone, code)
            
            database.add_account(phone, phone, TELEGRAM_API_ID, TELEGRAM_API_HASH, first_name, last_name)
            success = True
            return {"success": True, "phone": phone, "first_name": first_name}

        except SessionPasswordNeededError: return {"success": False, "error": "2FA Required"}
        except Exception as e: return {"success": False, "error": str(e)}
        finally:
            await client.disconnect()
            if not success:
                sp = f"{session_path}.session"
                if os.path.exists(sp): os.remove(sp)
