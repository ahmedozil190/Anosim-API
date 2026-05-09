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

class AccountCreator:
    def __init__(self, api_key):
        self.api = AnosimAPI(api_key)
        self.email_service = EmailService()

    async def start_purchase(self, product_id, provider_id=0):
        """Standard purchase flow. Clean and professional."""
        order = await self.api.create_order(product_id, provider_id=provider_id)
        bookings = order.get("orderBookings") or order.get("bookings")
        if not order or not bookings:
            return None, "Order failed on Anosim side"
        
        phone, bid = bookings[0]['number'], bookings[0]['id']
        session_path = os.path.join(SESSIONS_DIR, f"{phone}")
        if os.path.exists(f"{session_path}.session"): os.remove(f"{session_path}.session")

        # Stable client configuration
        client = TelegramClient(
            session_path, TELEGRAM_API_ID, TELEGRAM_API_HASH,
            device_model='Android Device',
            system_version='13.0',
            app_version='10.1.1'
        )
        await client.connect()
        return {"client": client, "phone": phone, "id": bid}, None

    async def request_code(self, client, phone):
        """Requests the code and identifies the verification type."""
        try:
            sent_code = await client.send_code_request(phone)
            # Check if Telegram requires email (App/Email types)
            needs_email = isinstance(sent_code.type, (types.auth.SentCodeTypeEmail, types.auth.SentCodeTypeApp))
            return sent_code, needs_email, None
        except Exception as e:
            if "email" in str(e).lower():
                return None, True, None
            return None, False, str(e)

    async def send_email_code(self, client, email, phone, sent_code=None):
        """Sends verification code using the correct TL purpose types."""
        try:
            # Determine if we need Login or Registration purpose
            is_app = sent_code and isinstance(sent_code.type, types.auth.SentCodeTypeApp)
            
            if is_app and sent_code and hasattr(sent_code, 'phone_code_hash'):
                purpose = types.EmailVerifyPurposeLogin(
                    phone_number=phone,
                    phone_code_hash=sent_code.phone_code_hash
                )
            else:
                purpose = types.EmailVerifyPurposeRegistration()

            # Execute request
            await client(functions.account.SendVerifyEmailCodeRequest(
                purpose=purpose,
                email=email
            ))
            return None
        except RPCError as e:
            logger.error(f"Telegram RPC Error: {e}")
            return f"Telegram Error: {e.message}"
        except Exception as e:
            logger.error(f"General Error: {e}")
            return str(e)

    async def verify_email_and_poll(self, client, email, code, phone):
        """Verifies the email and requests the SMS code again."""
        try:
            await client(functions.account.VerifyEmailRequest(email=email, code=code))
            # After email verification, Telegram allows sending the SMS code
            sent_code = await client.send_code_request(phone)
            return sent_code, None
        except Exception as e:
            return None, str(e)

    async def create_account_simple(self, client, phone, code, first_name="Ano", last_name="Sim"):
        """Finishes the authentication and saves the account."""
        try:
            # Try signing up first (for new numbers)
            try:
                await client.sign_up(code, first_name, last_name)
            except:
                # If already signed up, just sign in
                await client.sign_in(phone, code)
            
            database.add_account(phone, phone, TELEGRAM_API_ID, TELEGRAM_API_HASH, first_name, last_name)
            return True, None
        except SessionPasswordNeededError:
            return False, "2FA Password Required"
        except Exception as e:
            return False, str(e)

    async def bypass_to_sms(self, client, phone, sent_code):
        """Bypass strategy for recycled numbers."""
        try:
            # Mandatory wait for Telegram to allow resending as SMS
            await asyncio.sleep(65)
            new_sent_code = await client(functions.auth.ResendCodeRequest(
                phone_number=phone,
                phone_code_hash=sent_code.phone_code_hash
            ))
            return new_sent_code, None
        except Exception as e:
            return None, str(e)
