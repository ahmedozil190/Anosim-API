import httpx
import asyncio
import logging
import time
import random
import string

logger = logging.getLogger(__name__)

class EmailService:
    def __init__(self):
        self.base_url = "https://api.mail.tm"
        self.token = None
        self.address = None
        self.password = None
        self.account_id = None

    async def create_account(self):
        """Creates a new temporary email account"""
        async with httpx.AsyncClient() as client:
            # 1. Get domain
            resp = await client.get(f"{self.base_url}/domains")
            domains = resp.json().get("hydra:member")
            if not domains:
                return None
            domain = domains[0]['domain']

            # 2. Create account
            self.address = f"{''.join(random.choices(string.ascii_lowercase + string.digits, k=10))}@{domain}"
            self.password = "AnoSimPass123!"
            
            resp = await client.post(f"{self.base_url}/accounts", json={
                "address": self.address,
                "password": self.password
            })
            
            if resp.status_code != 201:
                logger.error(f"Failed to create email account: {resp.text}")
                return None
            
            self.account_id = resp.json().get("id")

            # 3. Get token
            resp = await client.post(f"{self.base_url}/token", json={
                "address": self.address,
                "password": self.password
            })
            self.token = resp.json().get("token")
            
            logger.info(f"Created temp email: {self.address}")
            return self.address

    async def get_messages(self):
        """Polls for messages in the inbox"""
        if not self.token:
            return []
        
        headers = {"Authorization": f"Bearer {self.token}"}
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{self.base_url}/messages", headers=headers)
            if resp.status_code == 200:
                return resp.json().get("hydra:member", [])
            return []

    async def wait_for_code(self, timeout=60):
        """Waits for a 6-digit or 5-digit code in the email"""
        start_time = time.time()
        logger.info(f"Waiting for email verification code on {self.address}...")
        
        while time.time() - start_time < timeout:
            messages = await self.get_messages()
            for msg in messages:
                # Get full message content
                headers = {"Authorization": f"Bearer {self.token}"}
                async with httpx.AsyncClient() as client:
                    msg_resp = await client.get(f"{self.base_url}/messages/{msg['id']}", headers=headers)
                    content = msg_resp.json().get("text", "")
                    # Search for 6-digit code (common for Telegram email verification)
                    import re
                    match = re.search(r'\b(\d{6})\b', content)
                    if match:
                        logger.info(f"Received email code: {match.group(1)}")
                        return match.group(1)
                    
            await asyncio.sleep(5)
        
        return None
