import httpx
import logging
from config import ANOSIM_API_KEY, ANOSIM_BASE_URL

logger = logging.getLogger(__name__)

class AnosimAPI:
    def __init__(self, api_key=ANOSIM_API_KEY):
        self.api_key = api_key
        self.base_url = ANOSIM_BASE_URL

    async def _get(self, endpoint, params=None):
        if params is None:
            params = {}
        params['apikey'] = self.api_key
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(f"{self.base_url}{endpoint}", params=params)
                if response.status_code != 200:
                    logger.error(f"Anosim API Error {response.status_code}: {response.text}")
                    return response.json() if response.headers.get("Content-Type") == "application/json" else None
                return response.json()
            except Exception as e:
                logger.error(f"Exception in Anosim API GET {endpoint}: {e}")
                return None

    async def _post(self, endpoint, params=None):
        if params is None:
            params = {}
        params['apikey'] = self.api_key
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(f"{self.base_url}{endpoint}", params=params)
                if response.status_code != 200:
                    logger.error(f"Anosim API Error {response.status_code}: {response.text}")
                    try:
                        return response.json()
                    except:
                        return None
                
                result = response.json()
                logger.info(f"Anosim API POST {endpoint} Success. Response: {result}")
                return result
            except Exception as e:
                logger.error(f"Exception in Anosim API POST {endpoint}: {e}")
                return None

    async def get_balance(self):
        """Returns account balance in USD"""
        data = await self._get("/Balance")
        return data.get("accountBalanceInUSD") if data else None

    async def get_countries(self):
        """Returns list of all countries"""
        return await self._get("/Countries")

    async def get_products(self, country_id=None):
        """Returns all products, optionally filtered by countryId"""
        params = {}
        if country_id:
            params['countryId'] = country_id
        return await self._get("/Products", params=params)

    async def get_product_details(self, product_id):
        """Returns detailed product info including providers"""
        return await self._get(f"/Products/{product_id}")

    async def create_order(self, product_id, amount=1, provider_id=0):
        """Creates an order. Returns order data with bookings list."""
        params = {
            'productId': product_id,
            'amount': amount,
            'providerId': provider_id,
            'maxPrice': 0
        }
        return await self._post("/Orders", params=params)

    async def get_sms(self, order_booking_id):
        """Returns SMS messages for a specific order booking ID"""
        return await self._get(f"/Sms/{order_booking_id}")

    async def get_order_booking(self, booking_id):
        """Returns details of a specific order booking"""
        return await self._get(f"/OrderBookings/{booking_id}")

    async def cancel_order_booking(self, booking_id):
        """Cancels an activation order booking"""
        params = {'apikey': self.api_key}
        async with httpx.AsyncClient() as client:
            try:
                response = await client.patch(f"{self.base_url}/OrderBookings/{booking_id}", params=params)
                response.raise_for_status()
                return response.json().get("success", False)
            except Exception as e:
                logger.error(f"Error canceling order booking {booking_id}: {e}")
                return False
