from flask import Flask, redirect, request, render_template_string, abort, jsonify
import os
import requests
from urllib.parse import quote_plus
from config import HCAPTCHA_SITE_KEY, HCAPTCHA_SECRET_KEY, SHORTERNER_URL, URLSHORTX_API_TOKEN
from database import get_ticket_sync, delete_ticket_sync

app = Flask(__name__)

# --- Helper for URL Shortener ---
def shorten_url_sync(url):
    """Synchronous version of the URL shortener function."""
    if not SHORTERNER_URL or not URLSHORTX_API_TOKEN:
        # If shortener is not configured, return the long URL
        return url

    api_url = f"https://{SHORTERNER_URL}/api"
    params = {'api': URLSHORTX_API_TOKEN, 'url': url}
    try:
        res = requests.get(api_url, params=params)
        res.raise_for_status()
        return res.json().get('shortenedUrl', url)
    except requests.exceptions.RequestException as e:
        print(f"Error shortening URL: {e}")
        return url

# --- Flask Routes ---

@app.route('/')
def hello_world():
    return '⚡️ Your App is Running ⚡️'

@app.route('/verify')
def verify_page():
    ticket_id = request.args.get('ticket')
    if not ticket_id:
        return abort(400, "Missing 'ticket' parameter.")

    if not HCAPTCHA_SITE_KEY or "ffff" in HCAPTCHA_SITE_KEY: # Basic check for dummy key
        return "Error: HCAPTCHA_SITE_KEY is not configured on the server."

    html_content = f"""
    <!DOCTYPE html>
    <html>
        <head>
            <title>Verification</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body {{ font-family: sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; background: #f4f6f9; }}
                .container {{ background: #fff; padding: 2rem; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); text-align: center; }}
                h1 {{ margin-bottom: 1rem; color: #333; }}
                p {{ margin-bottom: 1.5rem; color: #666; }}
                #submit-btn {{ background-color: #007bff; color: white; padding: 0.8rem 1.5rem; border: none; border-radius: 5px; cursor: pointer; font-size: 1rem; }}
                #submit-btn:hover {{ background-color: #0056b3; }}
            </style>
            <script src="https://js.hcaptcha.com/1/api.js" async defer></script>
        </head>
        <body>
            <div class="container">
                <h1>Please Verify</h1>
                <p>Complete the challenge to continue.</p>
                <form action="/solve" method="POST">
                    <input type="hidden" name="ticket_id" value="{ticket_id}">
                    <div class="h-captcha" data-sitekey="{HCAPTCHA_SITE_KEY}"></div>
                    <br>
                    <button type="submit" id="submit-btn">Submit</button>
                </form>
            </div>
        </body>
    </html>
    """
    return render_template_string(html_content)

@app.route('/solve', methods=['POST'])
def solve_captcha():
    ticket_id = request.form.get('ticket_id')
    captcha_response = request.form.get('h-captcha-response')

    if not ticket_id or not captcha_response:
        return abort(400, "Invalid request.")

    if not HCAPTCHA_SECRET_KEY or "0x0000" in HCAPTCHA_SECRET_KEY: # Basic check for dummy key
        return "Error: HCaptcha is not configured correctly on the server."

    # 1. Verify Captcha Response
    verification_data = {
        'secret': HCAPTCHA_SECRET_KEY,
        'response': captcha_response,
    }
    try:
        verify_res = requests.post('https://hcaptcha.com/siteverify', data=verification_data)
        verify_res.raise_for_status()
        verification_result = verify_res.json()
    except requests.exceptions.RequestException as e:
        return f"Error verifying captcha: {e}", 500

    if not verification_result.get('success'):
        return "Captcha verification failed. Please try again.", 400

    # 2. Get Ticket from Database
    ticket_data = get_ticket_sync(ticket_id)
    if not ticket_data:
        return "This verification ticket is invalid or has expired. Please request a new one from the bot.", 400

    user_token = ticket_data.get('user_token')
    if not user_token:
         return "Ticket data is corrupted. Please request a new one.", 500

    # 3. Create the Final Bot Link & Shorten It
    # This assumes your bot username is known or can be retrieved.
    # For now, let's hardcode a placeholder. You should pass this in or configure it.
    BOT_USERNAME = os.getenv('BOT_USERNAME', '') # Add BOT_USERNAME to your config.env
    bot_deep_link = f'https://telegram.dog/{BOT_USERNAME}?start=token_{user_token}'

    final_url = shorten_url_sync(bot_deep_link)

    # 4. Invalidate the ticket and redirect
    delete_ticket_sync(ticket_id)

    return redirect(final_url)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
