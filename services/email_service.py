import httpx
import asyncio
import logging
import time
import random
import string
import re

logger = logging.getLogger(__name__)


class EmailService:
    def __init__(self):
        self.base_url = "https://api.mail.tm"
        self.token = None
        self.address = None
        self.password = None
        self.account_id = None

    async def create_account(self):
        """Creates a new temporary email account using mail.tm API."""
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                # 1. Get available domain
                resp = await client.get(f"{self.base_url}/domains")
                resp.raise_for_status()
                domains = resp.json().get("hydra:member", [])
                if not domains:
                    logger.error("No domains available from mail.tm")
                    return None
                domain = domains[0]['domain']

                # 2. Create random email account
                username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=12))
                self.address = f"{username}@{domain}"
                self.password = "AnoSim@2024!"

                resp = await client.post(f"{self.base_url}/accounts", json={
                    "address": self.address,
                    "password": self.password
                })

                if resp.status_code != 201:
                    logger.error(f"Failed to create email: {resp.status_code} {resp.text}")
                    return None

                self.account_id = resp.json().get("id")

                # 3. Get auth token
                resp = await client.post(f"{self.base_url}/token", json={
                    "address": self.address,
                    "password": self.password
                })
                resp.raise_for_status()
                self.token = resp.json().get("token")

                logger.info(f"Created temp email: {self.address}")
                return self.address

        except Exception as e:
            logger.error(f"Email creation failed: {e}")
            return None

    async def get_messages(self):
        """Polls the inbox for new messages."""
        if not self.token:
            return []
        try:
            headers = {"Authorization": f"Bearer {self.token}"}
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(f"{self.base_url}/messages", headers=headers)
                if resp.status_code == 200:
                    return resp.json().get("hydra:member", [])
        except Exception as e:
            logger.error(f"Failed to get messages: {e}")
        return []

    async def wait_for_code(self, timeout=90):
        """Waits for a verification code in the inbox."""
        start = time.time()
        logger.info(f"Waiting for email code on {self.address}...")

        while time.time() - start < timeout:
            messages = await self.get_messages()
            for msg in messages:
                try:
                    headers = {"Authorization": f"Bearer {self.token}"}
                    async with httpx.AsyncClient(timeout=15) as client:
                        msg_resp = await client.get(
                            f"{self.base_url}/messages/{msg['id']}",
                            headers=headers
                        )
                        content = msg_resp.json().get("text", "") + msg_resp.json().get("html", "")
                        # Look for 5 or 6 digit codes
                        match = re.search(r'\b(\d{5,6})\b', content)
                        if match:
                            code = match.group(1)
                            logger.info(f"Email code found: {code}")
                            return code
                except Exception as e:
                    logger.error(f"Error reading message: {e}")

            await asyncio.sleep(5)

        logger.warning(f"Email code timeout after {timeout}s")
        return None
