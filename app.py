from flask import Flask, redirect, request, render_template_string, abort
import os
import urllib.parse
import asyncio
import aiohttp
import secrets # For generating secure short codes
from time import time as tm
from config import URLSHORTX_API_TOKEN, SHORTERNER_URL, logger # Import from config

app = Flask(__name__)

# Temporary storage for custom short codes
# In a real-world scenario, this should be a database (e.g., MongoDB, Redis)
# as Flask apps on Koyeb might be stateless or scale with multiple instances.
# For single instance, this is a quick way. Add a cleanup mechanism for expired codes.
custom_short_links = {} # {custom_short_code: {'bot_deep_link': '...', 'timestamp': tm()}}

# This function is duplicated from shorterner.py, or you can find a way to import it.
async def _shorten_url_server_side(url):
    try:
        api_url = f"https://{SHORTERNER_URL}/api"
        params = {
            "api": URLSHORTX_API_TOKEN,
            "url": url,
            "format": "text"
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, params=params) as response:
                if response.status == 200:
                    return (await response.text()).strip()
                else:
                    logger.error(
                        f"URL shortening failed from Flask. Status code: {response.status}, Response: {await response.text()}"
                    )
                    return url # Fallback to original if shortening fails
    except Exception as e:
        logger.error(f"URL shortening failed from Flask: {e}")
        return url # Fallback to original if shortening fails


@app.route('/')
def hello_world():
    return '⚡Your App is Running⚡'

@app.route('/link/<custom_short_code>') # New route for custom short links
async def custom_short_link_handler(custom_short_code):
    link_info = custom_short_links.get(custom_short_code)

    if not link_info:
        logger.warning(f"Invalid custom_short_code accessed: {custom_short_code}")
        abort(404) # Not found

    # Check for expiration (e.g., 1 hour for the custom short code to be valid)
    CUSTOM_SHORT_CODE_TIMEOUT = 3600 # 1 hour
    if tm() - link_info['timestamp'] > CUSTOM_SHORT_CODE_TIMEOUT:
        logger.warning(f"Expired custom_short_code: {custom_short_code}")
        # Optionally remove from dict to clean up
        custom_short_links.pop(custom_short_code, None) 
        return "This link has expired. Please request a new token from the bot.", 400

    # Human Gate Page (the "Click Here" part)
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Human Verification</title>
        <style>
            body {{ font-family: sans-serif; display: flex; flex-direction: column; justify-content: center; align-items: center; height: 100vh; margin: 0; background-color: #f0f2f5; }}
            .container {{ background-color: #ffffff; padding: 40px; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); text-align: center; }}
            h1 {{ color: #333; margin-bottom: 20px; }}
            p {{ color: #666; margin-bottom: 30px; }}
            .button {{ background-color: #007bff; color: white; padding: 15px 30px; border: none; border-radius: 5px; cursor: pointer; font-size: 1.1em; text-decoration: none; transition: background-color 0.3s ease; }}
            .button:hover {{ background-color: #0056b3; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Human Verification</h1>
            <p>Klik di bawah untuk melanjutkan ke proses verifikasi token. Ini membantu kami memastikan Anda bukan bot.</p>
            <a href="/redirect_from_gate/{custom_short_code}" class="button">Click Here to Proceed</a>
        </div>
    </body>
    </html>
    """
    return render_template_string(html_content)

@app.route('/redirect_from_gate/<custom_short_code>')
async def redirect_from_gate(custom_short_code):
    link_info = custom_short_links.pop(custom_short_code, None) # Use once, then remove

    if not link_info:
        logger.warning(f"Invalid or already used custom_short_code for redirect: {custom_short_code}")
        return "This link has expired or is invalid. Please request a new token from the bot.", 400

    # Re-check for expiration here as well
    CUSTOM_SHORT_CODE_TIMEOUT = 3600 # 1 hour
    if tm() - link_info['timestamp'] > CUSTOM_SHORT_CODE_TIMEOUT:
        logger.warning(f"Expired custom_short_code during redirect: {custom_short_code}")
        return "This link has expired. Please request a new token from the bot.", 400

    bot_deep_link = link_info['bot_deep_link']

    # Now, shorten the original bot deep link using the external shortener (server-side)
    shortened_url_from_external = await _shorten_url_server_side(bot_deep_link)
    
    logger.info(f"Flask server-side redirecting user to external shortener: {shortened_url_from_external}")
    return redirect(shortened_url_from_external)


if __name__ == "__main__":
    app.run()
