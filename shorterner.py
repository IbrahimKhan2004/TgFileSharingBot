import aiohttp
from config import *

async def shorten_url(url, base_site=None, api_token=None):
    try:
        site = base_site if base_site else SHORTERNER_URL
        token = api_token if api_token else URLSHORTX_API_TOKEN

        api_url = f"https://{site}/api"
        params = {
            "api": token,
            "url": url,
            "format": "text"
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, params=params) as response:
                if response.status == 200:
                    return (await response.text()).strip()
                else:
                    logger.error(
                        f"URL shortening failed. Status code: {response.status}, Response: {await response.text()}"
                    )
                    return url
    except Exception as e:
        logger.error(f"URL shortening failed: {e}")
        return url
    