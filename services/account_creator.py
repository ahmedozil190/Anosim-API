import asyncio
import logging
import os
import re
from telethon import TelegramClient, functions, types
from telethon.tl.types import EmailVerificationCode
from telethon.errors import (
    SessionPasswordNeededError, RPCError,
    PhoneCodeInvalidError, PhoneCodeExpiredError
)
from services.anosim_api import AnosimAPI
from services.email_service import EmailService
from config import TELEGRAM_API_ID, TELEGRAM_API_HASH, SESSIONS_DIR
import database

logger = logging.getLogger(__name__)

MAX_RETRIES = 3  # How many numbers to try before giving up


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

    async def _buy_number(self, product_id, provider_id):
        """Buy a number and return (phone, booking_id) or raise on failure."""
        order = await self.api.create_order(product_id, provider_id=provider_id)
        bookings = order.get("orderBookings") or order.get("bookings")
        if not order or not bookings:
            raise RuntimeError("Failed to buy number from Anosim")
        return bookings[0]['number'], bookings[0]['id']

    async def create_account(self, country_id, product_id, first_name, last_name,
                              provider_id=0, status_callback=None):
        """
        Fully automated account creation with auto-retry.
        If a number requires an inaccessible email or is blocked,
        the bot cancels the booking, buys a fresh number and retries.
        """
        last_error = "Unknown error"

        for attempt_num in range(1, MAX_RETRIES + 1):
            logger.info(f"Account creation attempt {attempt_num}/{MAX_RETRIES}")
            result = await self._try_create(
                product_id, first_name, last_name,
                provider_id, status_callback, attempt_num
            )
            if result["success"]:
                return result
            last_error = result["error"]
            logger.warning(f"Attempt {attempt_num} failed: {last_error}")

            # Don't retry for errors that retrying won't fix
            if any(x in last_error for x in ["2FA", "Sign-in failed", "SMS timeout"]):
                break

        return {"success": False, "error": f"(بعد {MAX_RETRIES} محاولات): {last_error}"}

    async def _try_create(self, product_id, first_name, last_name,
                          provider_id, status_callback, attempt_num):
        """Single attempt to buy a number and create an account."""

        # --- Step 1: Buy Number ---
        try:
            phone, bid = await self._buy_number(product_id, provider_id)
        except Exception as e:
            return {"success": False, "error": str(e)}

        logger.info(f"Bought number: {phone} (booking: {bid})")

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
            logger.info(f"Code type: {code_type}")

            # --- Step 4: Handle code type ---
            if code_type == 'SentCodeTypeSms':
                # Best case — SMS sent directly, nothing to do
                pass

            elif code_type == 'SentCodeTypeEmailCode':
                # This number had an old account with a linked email.
                # We don't have access to that email.
                # Try once to force SMS via ResendCodeRequest.
                logger.info("SentCodeTypeEmailCode — trying to force SMS via ResendCodeRequest...")
                try:
                    sent_code = await client(functions.auth.ResendCodeRequest(
                        phone_number=phone,
                        phone_code_hash=sent_code.phone_code_hash
                    ))
                    new_type = type(sent_code.type).__name__
                    logger.info(f"ResendCode returned: {new_type}")
                    if new_type != 'SentCodeTypeSms':
                        # Still not SMS — cancel and retry with a new number
                        await self.api.cancel_order_booking(bid)
                        return {"success": False,
                                "error": f"الرقم مربوط بإيميل قديم ولا يمكن تجاوزه، جاري شراء رقم آخر..."}
                except RPCError as e:
                    logger.error(f"ResendCodeRequest failed: {e}")
                    await self.api.cancel_order_booking(bid)
                    return {"success": False,
                            "error": f"الرقم مربوط بإيميل قديم ولا يمكن تجاوزه، جاري شراء رقم آخر..."}

            else:
                # SentCodeTypeApp, MissedCall, or other — try to force SMS
                logger.info(f"Code type '{code_type}' — trying ResendCodeRequest for SMS...")
                try:
                    sent_code = await client(functions.auth.ResendCodeRequest(
                        phone_number=phone,
                        phone_code_hash=sent_code.phone_code_hash
                    ))
                    logger.info(f"ResendCode returned: {type(sent_code.type).__name__}")
                except RPCError as e:
                    logger.error(f"ResendCodeRequest failed: {e}")
                    await self.api.cancel_order_booking(bid)
                    return {"success": False,
                            "error": f"تيليجرام رفض إرسال SMS للرقم، جاري شراء رقم آخر..."}

            # --- Step 5: Poll SMS from Anosim ---
            code = None
            for poll_attempt in range(1, 21):
                if status_callback:
                    await status_callback('status_waiting', phone=phone, id=bid,
                                          attempt=poll_attempt, total=20)
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
                except (PhoneCodeInvalidError, PhoneCodeExpiredError) as e:
                    return {"success": False, "error": f"Sign-in failed: {e}"}
                except Exception as e:
                    return {"success": False, "error": f"Sign-in failed: {e}"}

            # --- Step 7: Save Account ---
            database.add_account(phone, phone, TELEGRAM_API_ID, TELEGRAM_API_HASH,
                                  first_name, last_name)
            return {"success": True, "phone": phone, "first_name": first_name}

        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            # Try to cancel booking on unexpected errors
            try:
                await self.api.cancel_order_booking(bid)
            except Exception:
                pass
            return {"success": False, "error": str(e)}

        finally:
            await client.disconnect()
            # Clean up failed session files
            sp2 = f"{session_path}.session"
            if os.path.exists(sp2) and not database.get_account(phone):
                os.remove(sp2)
