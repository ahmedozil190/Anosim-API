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

            # --- Step 4: Handle Email Verification (if required) ---
            # Telegram sends email verification for "recycled" numbers that had accounts
            if code_type in ('SentCodeTypeEmailCode', 'SentCodeTypeMissedCall'):
                # SentCodeTypeEmailCode means Telegram wants to send code to a linked email
                # We need to handle this differently - just poll for SMS resend
                logger.info("Email code type detected, attempting SMS bypass...")
                await asyncio.sleep(65)
                try:
                    sent_code = await client(functions.auth.ResendCodeRequest(
                        phone_number=phone,
                        phone_code_hash=sent_code.phone_code_hash
                    ))
                    logger.info(f"After resend, new code type: {type(sent_code.type).__name__}")
                except Exception as e:
                    logger.error(f"Resend failed: {e}")
                    return {"success": False, "error": f"SMS bypass failed: {e}"}

            elif code_type == 'SentCodeTypeApp':
                # App-based code — requires email verification via account.sendVerifyEmailCode
                # This uses EmailVerifyPurposeLoginSetup (the CORRECT type for new registrations)
                logger.info("App code type detected, using email verification flow...")
                email_service = self._new_email_service()
                email = await email_service.create_account()

                if not email:
                    return {"success": False, "error": "Failed to create temporary email"}

                if status_callback:
                    await status_callback('status_email_created', phone=phone, id=bid, email=email)

                try:
                    # Use the CORRECT purpose: EmailVerifyPurposeLoginSetup
                    await client(functions.account.SendVerifyEmailCodeRequest(
                        purpose=EmailVerifyPurposeLoginSetup(),
                        email=email
                    ))

                    # Poll for the verification code in the email inbox
                    email_code = await email_service.wait_for_code(timeout=60)

                    if not email_code:
                        logger.warning("Email code not received, attempting SMS bypass...")
                        await asyncio.sleep(65)
                        sent_code = await client(functions.auth.ResendCodeRequest(
                            phone_number=phone,
                            phone_code_hash=sent_code.phone_code_hash
                        ))
                    else:
                        # Verify the email code using correct API signature:
                        # VerifyEmailRequest(purpose, verification)
                        await client(functions.account.VerifyEmailRequest(
                            purpose=EmailVerifyPurposeLoginSetup(),
                            verification=EmailVerificationCode(code=email_code)
                        ))
                        if status_callback:
                            await status_callback('status_email_success', phone=phone, id=bid, email=email)

                        # Now request the phone code via SMS
                        await asyncio.sleep(2)
                        sent_code = await client.send_code_request(phone)

                except RPCError as e:
                    logger.error(f"Email verification RPC error: {e}")
                    # Fall back to SMS bypass
                    await asyncio.sleep(65)
                    sent_code = await client(functions.auth.ResendCodeRequest(
                        phone_number=phone,
                        phone_code_hash=sent_code.phone_code_hash
                    ))

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
