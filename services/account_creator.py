import asyncio
import logging
import os
import re
import random
from telethon import TelegramClient, functions
from telethon.tl.types import (
    EmailVerifyPurposeLoginSetup,
    EmailVerificationCode,
)
from telethon.errors import SessionPasswordNeededError, RPCError
from services.anosim_api import AnosimAPI
from services.email_service import EmailService
from config import TELEGRAM_API_ID, TELEGRAM_API_HASH, SESSIONS_DIR, PROXY_HOST, PROXY_PORT, PROXY_USER, PROXY_PASS
import database

logger = logging.getLogger(__name__)

MAX_RETRIES = 1  # Set to 1 to avoid burning money on blocked numbers


class AccountCreator:
    def __init__(self, api_key):
        self.api = AnosimAPI(api_key)

    def _make_client(self, session_path):
        # Build optional proxy for SMS-fee bypass using dict format
        proxy = None
        if PROXY_HOST:
            proxy = {
                'proxy_type': 'socks5',
                'addr': PROXY_HOST,
                'port': PROXY_PORT,
                'username': PROXY_USER or '',
                'password': PROXY_PASS or '',
                'rdns': True
            }
            logger.info(f"Using proxy: {PROXY_HOST}:{PROXY_PORT}")

        # Randomize device info to prevent fingerprinting
        models = ['Samsung SM-S918B', 'Samsung SM-G998B', 'Pixel 8 Pro', 'Pixel 7a', 'Xiaomi 13 Pro', 'OnePlus 11']
        sys_versions = ['12', '13', '14']
        app_versions = ['10.1.1', '10.2.0', '10.5.0', '9.7.0']

        device_model = random.choice(models)
        system_version = random.choice(sys_versions)
        app_version = random.choice(app_versions)
        logger.info(f"Device Profile: {device_model} / Android {system_version} / App {app_version}")

        return TelegramClient(
            session_path,
            TELEGRAM_API_ID,
            TELEGRAM_API_HASH,
            device_model=device_model,
            system_version=system_version,
            app_version=app_version,
            lang_code='en',
            system_lang_code='en-US',
            proxy=proxy,
        )

    async def create_account(self, country_id, product_id, first_name, last_name,
                              provider_id=0, status_callback=None):
        """Auto-retry account creation up to MAX_RETRIES times."""
        last_error = "Unknown error"

        for attempt_num in range(1, MAX_RETRIES + 1):
            if attempt_num > 1:
                logger.info(f"Retry attempt {attempt_num}/{MAX_RETRIES}...")

            result = await self._try_once(
                product_id, first_name, last_name,
                provider_id, status_callback
            )

            if result["success"]:
                return result

            last_error = result["error"]
            logger.warning(f"[Attempt {attempt_num}] Failed: {last_error}")

            # Some errors won't benefit from retrying
            if not result.get("retry", True):
                break

        return {"success": False, "error": f"فشل بعد {attempt_num} محاولات: {last_error}"}

    async def _try_once(self, product_id, first_name, last_name,
                        provider_id, status_callback):
        # ── Step 1: Buy Number ──────────────────────────────────────────
        order = await self.api.create_order(product_id, provider_id=provider_id)
        bookings = order.get("orderBookings") or order.get("bookings")
        if not order or not bookings:
            return {"success": False, "error": "Failed to buy number from Anosim", "retry": True}

        phone = bookings[0]['number']
        bid   = bookings[0]['id']
        logger.info(f"Bought number: {phone} (booking_id={bid})")

        if status_callback:
            await status_callback('status_bought', phone=phone, id=bid)

        # ── Step 2: Setup Client ────────────────────────────────────────
        session_path = os.path.join(SESSIONS_DIR, phone)
        sp = f"{session_path}.session"
        if os.path.exists(sp):
            os.remove(sp)

        client = self._make_client(session_path)

        try:
            await client.connect()

            # ── Step 3: Request Code ────────────────────────────────────
            if status_callback:
                await status_callback('status_requesting', phone=phone, id=bid)

            sent_code  = await client.send_code_request(phone)
            code_type  = type(sent_code.type).__name__
            phone_hash = sent_code.phone_code_hash
            logger.info(f"Telegram code type: {code_type}")

            # ── Step 4: Handle code type ────────────────────────────────
            if code_type == 'SentCodeTypeSms':
                # ✅ Best case — SMS already sent, nothing to do
                pass

            elif code_type == 'SentCodeTypeEmailCode':
                # This means: "Telegram wants email verification first, then SMS".
                # SentCodeTypeEmailCode = email-linked old account
                email_pattern = getattr(sent_code.type, 'email_pattern', '')
                logger.info(f"Code type '{code_type}' — email_pattern: '{email_pattern}' → starting email flow...")

                # Step A: Try to switch to SMS first (quick win if allowed)
                sms_sent_code, sms_ok = await self._force_sms(client, phone, phone_hash)
                if sms_ok and type(sms_sent_code.type).__name__ == 'SentCodeTypeSms':
                    logger.info("Switched to SMS via ResendCodeRequest!")
                    sent_code = sms_sent_code

                else:
                    # Step B: Email flow — create temp email, verify, then request SMS
                    logger.info("ResendCodeRequest didn't give SMS → starting temp email flow...")
                    email_service = EmailService()
                    email = await email_service.create_account()

                    if not email:
                        logger.error("Failed to create temp email.")
                        await self.api.cancel_order_booking(bid)
                        return {"success": False, "error": "فشل إنشاء الإيميل الوهمي", "retry": False}

                    if status_callback:
                        await status_callback('status_email_created', phone=phone, id=bid, email=email)

                    email_ok = await self._email_verify_flow(
                        client, phone, phone_hash, email, email_service,
                        status_callback, bid
                    )

                    if email_ok == "verified":
                        if status_callback:
                            await status_callback('status_email_success', phone=phone, id=bid, email=email)
                        await asyncio.sleep(2)
                        # Re-request code after email verification
                        sent_code = await client.send_code_request(phone)
                    else:
                        await self.api.cancel_order_booking(bid)
                        return {"success": False,
                                "error": f"فشل التحقق بالإيميل\nنوع الكود: {code_type}\nنمط الإيميل: {email_pattern or 'غير محدد'}",
                                "retry": False}

            else:
                # MissedCall, FlashCall, SentCodeTypeApp, etc.
                # DO NOT use email flow here! Telegram API strictly rejects SendVerifyEmailCodeRequest
                # for these types with "invalid phone_code_hash".
                logger.info(f"Code type '{code_type}' → requesting SMS via ResendCodeRequest...")
                sent_code, ok = await self._force_sms(client, phone, phone_hash)
                if not ok:
                    await self.api.cancel_order_booking(bid)
                    return {"success": False,
                            "error": f"❌ الرقم محظور من تيليجرام ({code_type})\n\n"
                                     f"📌 جرب مزوداً أو دولةً أخرى.",
                            "retry": False}

            # ── Step 5: Poll SMS from Anosim ────────────────────────────
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
                return {"success": False, "error": "لم يصل الكود عبر SMS", "retry": True}

            # ── Step 6: Sign In / Sign Up ───────────────────────────────
            try:
                await client.sign_up(code, first_name, last_name)
            except Exception:
                try:
                    await client.sign_in(phone, code)
                except SessionPasswordNeededError:
                    return {"success": False, "error": "2FA مفعّل على هذا الرقم", "retry": False}
                except Exception as e:
                    return {"success": False, "error": f"فشل تسجيل الدخول: {e}", "retry": False}

            # ── Step 7: Save ────────────────────────────────────────────
            database.add_account(phone, phone, TELEGRAM_API_ID, TELEGRAM_API_HASH,
                                  first_name, last_name)
            return {"success": True, "phone": phone, "first_name": first_name}

        except Exception as e:
            logger.error(f"Unexpected error on {phone}: {e}", exc_info=True)
            try:
                await self.api.cancel_order_booking(bid)
            except Exception:
                pass
            return {"success": False, "error": str(e), "retry": True}

        finally:
            await client.disconnect()
            sp2 = f"{session_path}.session"
            existing = [a for a in database.get_all_accounts() if a[0] == phone]
            if os.path.exists(sp2) and not existing:
                os.remove(sp2)

    # ── Helpers ─────────────────────────────────────────────────────────

    async def _email_verify_flow(self, client, phone, phone_hash, email,
                                  email_service, status_callback, bid):
        """
        Try to verify via a temp email.
        Returns: 'verified', 'sms_fallback', or 'timeout'
        """
        try:
            await client(functions.account.SendVerifyEmailCodeRequest(
                purpose=EmailVerifyPurposeLoginSetup(
                    phone_number=phone,
                    phone_code_hash=phone_hash
                ),
                email=email
            ))
        except RPCError as e:
            logger.error(f"SendVerifyEmailCodeRequest rejected: {e}")
            return "sms_fallback"

        # Wait for code in temp email inbox
        email_code = await email_service.wait_for_code(timeout=90)

        if not email_code:
            logger.warning("No email code received within timeout.")
            return "timeout"

        # Verify the code
        try:
            await client(functions.account.VerifyEmailRequest(
                purpose=EmailVerifyPurposeLoginSetup(
                    phone_number=phone,
                    phone_code_hash=phone_hash
                ),
                verification=EmailVerificationCode(code=email_code)
            ))
            logger.info("Email verification successful!")
            return "verified"
        except RPCError as e:
            logger.error(f"VerifyEmailRequest failed: {e}")
            return "sms_fallback"

    async def _force_sms(self, client, phone, phone_hash):
        """
        Try to switch to SMS via ResendCodeRequest.
        Returns: (sent_code, True) on success, (None, False) on failure.
        """
        try:
            sent_code = await client(functions.auth.ResendCodeRequest(
                phone_number=phone,
                phone_code_hash=phone_hash
            ))
            new_type = type(sent_code.type).__name__
            logger.info(f"ResendCodeRequest → {new_type}")
            return sent_code, True
        except RPCError as e:
            logger.error(f"ResendCodeRequest failed: {e}")
            return None, False
