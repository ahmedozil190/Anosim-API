import asyncio
import logging
import os
import re
from telethon import TelegramClient, functions, types
from telethon.tl.types import (
    EmailVerifyPurposeLoginSetup,
    EmailVerifyPurposeLoginChange,
    EmailVerificationCode,
)
from telethon.errors import SessionPasswordNeededError, RPCError
from services.anosim_api import AnosimAPI
from services.email_service import EmailService
from config import TELEGRAM_API_ID, TELEGRAM_API_HASH, SESSIONS_DIR
import database

logger = logging.getLogger(__name__)


class AccountCreator:
    def __init__(self, api_key):
        self.api = AnosimAPI(api_key)

    def _new_email_service(self):
        return EmailService()

    def _make_client(self, session_path):
        return TelegramClient(
            session_path,
            TELEGRAM_API_ID,
            TELEGRAM_API_HASH,
            device_model='Samsung SM-S918B',
            system_version='13',
            app_version='10.1.1',
            lang_code='en',
            system_lang_code='en-US',
        )

    async def create_account(self, country_id, product_id, first_name, last_name,
                              provider_id=0, status_callback=None):
        """Fully automated account creation with correct Telegram email verification."""

        # --- Step 1: Buy Number ---
        order = await self.api.create_order(product_id, provider_id=provider_id)
        bookings = order.get("orderBookings") or order.get("bookings")
        if not order or not bookings:
            return {"success": False, "error": "Failed to buy number from Anosim"}

        phone = bookings[0]['number']
        bid = bookings[0]['id']

        if status_callback:
            await status_callback('status_bought', phone=phone, id=bid)

        # --- Step 2: Setup Client ---
        session_path = os.path.join(SESSIONS_DIR, phone)
        sp = f"{session_path}.session"
        if os.path.exists(sp):
            os.remove(sp)

        client = self._make_client(session_path)

        try:
            await client.connect()

            # --- Step 3: Request Code ---
            if status_callback:
                await status_callback('status_requesting', phone=phone, id=bid)

            sent_code = await client.send_code_request(phone)
            code_type = type(sent_code.type).__name__
            logger.info(f"Telegram code type: {code_type}")

            # --- Step 4: Handle non-SMS code types ---
            # Telegram may return EmailCode, App or MissedCall type for recycled numbers.
            # The ONLY reliable way to get an SMS is to call ResendCodeRequest.
            # SendVerifyEmailCodeRequest is for recovery-email setup and CANNOT be used here.
            
            if code_type != 'SentCodeTypeSms':
                logger.info(f"Code type is '{code_type}'. Requesting SMS via ResendCodeRequest...")
                
                if status_callback and code_type == 'SentCodeTypeEmailCode':
                    # Show the email field with a note that we're bypassing it
                    await status_callback('status_email_created', phone=phone, id=bid,
                                         email="Bypassing... waiting for SMS")

                # Wait before requesting resend (Telegram rate limits)
                await asyncio.sleep(5)
                try:
                    sent_code = await client(functions.auth.ResendCodeRequest(
                        phone_number=phone,
                        phone_code_hash=sent_code.phone_code_hash
                    ))
                    new_type = type(sent_code.type).__name__
                    logger.info(f"ResendCodeRequest successful. New code type: {new_type}")
                except RPCError as e:
                    logger.error(f"ResendCodeRequest failed: {e}")
                    await self.api.cancel_order_booking(bid)
                    return {"success": False, "error": f"رقم محظور - تيليجرام رفض إرسال SMS: {e}"}

            # --- Step 5: Poll SMS from Anosim ---
            code = None
            for attempt in range(1, 21):
                if status_callback:
                    await status_callback('status_waiting', phone=phone, id=bid,
                                          attempt=attempt, total=20)
                await asyncio.sleep(15)
                sms_list = await self.api.get_sms(bid)
                if sms_list:
                    for sms in sms_list:
                        match = re.search(r'\b(\d{5,6})\b', sms.get('messageText', ''))
                        if match:
                            code = match.group(1)
                            break
                if code:
                    break

            if not code:
                await self.api.cancel_order_booking(bid)
                return {"success": False, "error": "SMS timeout — no code received"}

            # --- Step 6: Sign In / Sign Up ---
            try:
                await client.sign_up(code, first_name, last_name)
            except Exception:
                try:
                    await client.sign_in(phone, code)
                except SessionPasswordNeededError:
                    return {"success": False, "error": "2FA is enabled on this number"}
                except Exception as e:
                    return {"success": False, "error": f"Sign-in failed: {e}"}

            # --- Step 7: Save Account ---
            database.add_account(phone, phone, TELEGRAM_API_ID, TELEGRAM_API_HASH,
                                  first_name, last_name)
            return {"success": True, "phone": phone, "first_name": first_name}

        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

        finally:
            await client.disconnect()
            if not os.path.exists(os.path.join(SESSIONS_DIR, f"{phone}.session")):
                # Clean up failed session files
                sp2 = f"{session_path}.session"
                if os.path.exists(sp2):
                    os.remove(sp2)
