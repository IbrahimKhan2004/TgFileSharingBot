from quart import Quart, request, render_template_string, redirect
import os
import urllib.parse
from database import get_shortener_link_async, update_gate_ip, process_ip_check
from config import BOT_USERNAME

app = Quart(__name__)

def get_client_ip():
    if request.headers.getlist("X-Forwarded-For"):
        return request.headers.getlist("X-Forwarded-For")[0]
    return request.remote_addr

@app.route('/')
async def hello_world():
    return '⚡Your App is Running⚡'

@app.route('/gate')
async def human_gate():
    request_id = request.args.get('id')

    # We just need to check for the ID and pass it to the template.
    # The actual link lookup will happen in the /verify endpoint.
    if not request_id:
        return "Invalid request. Missing ID.", 400

    client_ip = get_client_ip()
    await update_gate_ip(request_id, client_ip)

    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Human Verification</title>
        <style>
            body { font-family: sans-serif; display: flex; flex-direction: column; justify-content: center; align-items: center; height: 100vh; margin: 0; background-color: #f0f2f5; }
            .container { background-color: #ffffff; padding: 40px; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); text-align: center; display: none; }
            .warning-container { background-color: #fff3cd; color: #856404; padding: 40px; border-radius: 8px; border: 1px solid #ffeeba; box-shadow: 0 4px 8px rgba(0,0,0,0.1); text-align: center; display: none; max-width: 80%; }
            h1 { color: #333; margin-bottom: 20px; }
            p { color: #666; margin-bottom: 30px; }
            .button { display: inline-block; background-color: #007bff; color: white; padding: 15px 30px; border: none; border-radius: 5px; cursor: pointer; font-size: 1.1em; text-decoration: none; transition: background-color 0.3s ease; }
            .button:hover { background-color: #0056b3; }
            .warning-text { font-size: 1.2em; font-weight: bold; margin-bottom: 10px; }
        </style>
    </head>
    <body>
        <div id="main-container" class="container">
            <h1>Human Verification</h1>
            <p>Click below to proceed to the token verification process. This helps us ensure you are not a bot.</p>
            <a href="/verify/{{ request_id }}" class="button">Click Here to Proceed</a>
        </div>

        <div id="warning-container" class="warning-container">
            <p class="warning-text">Please open this link in Google Chrome to proceed.</p>
            <p class="warning-text">Kripya is link ko Google Chrome me khole.</p>
        </div>

        <script>
            async function checkBrowser() {
                let isChrome = false;
                const ua = navigator.userAgent;
                const vendor = navigator.vendor;

                // 1. Brave Detection (High Priority) - Explicit Block
                if (navigator.brave && await navigator.brave.isBrave()) {
                    showWarning();
                    return;
                }

                // 2. iOS Chrome Check (CriOS) - WebKit based, no Client Hints
                if (/CriOS/.test(ua)) {
                    isChrome = true;
                }
                // 3. Modern Client Hints API (Desktop/Android)
                else if (navigator.userAgentData && navigator.userAgentData.brands) {
                    const brands = navigator.userAgentData.brands;
                    const hasGoogleChrome = brands.some(b => b.brand === 'Google Chrome');
                    const hasEdge = brands.some(b => b.brand === 'Microsoft Edge');
                    const hasOpera = brands.some(b => b.brand === 'Opera');
                    const hasBrave = brands.some(b => b.brand === 'Brave');

                    // Must be Google Chrome and NOT Edge/Opera/Brave
                    if (hasGoogleChrome && !hasEdge && !hasOpera && !hasBrave) {
                        isChrome = true;
                    }
                }
                // 4. Legacy Fallback (Regex)
                else {
                    const isGenericChrome = /Chrome/.test(ua) && /Google Inc/.test(vendor);
                    const isEdge = /Edg/.test(ua);
                    const isOpera = /OPR/.test(ua);

                    if (isGenericChrome && !isEdge && !isOpera) {
                        isChrome = true;
                    }
                }

                if (isChrome) {
                    showMain();
                } else {
                    showWarning();
                }
            }

            function showMain() {
                document.getElementById('main-container').style.display = 'block';
                document.getElementById('warning-container').style.display = 'none';
            }

            function showWarning() {
                document.getElementById('main-container').style.display = 'none';
                document.getElementById('warning-container').style.display = 'block';
            }

            checkBrowser();
        </script>
    </body>
    </html>
    """
    return await render_template_string(html_content, request_id=request_id)


@app.route('/verify/<request_id>')
async def verify_redirect(request_id):
    """
    This endpoint fetches the shortener URL and redirects the user.
    This prevents the shortener URL from being exposed on the client-side.
    """
    if not request_id:
        return "Invalid request. Missing ID.", 400

    shortener_redirect_url = await get_shortener_link_async(request_id)
    if not shortener_redirect_url:
        return "Invalid ID or link expired.", 404

    # Perform the server-side redirect
    return redirect(shortener_redirect_url)

@app.route('/final')
async def final_check():
    token = request.args.get('token')

    if not token:
        return "Invalid request. Missing Token.", 400

    client_ip = get_client_ip()
    await process_ip_check(token, client_ip)

    # Fallback/Safe logic: Always allow user to proceed to bot,
    # but the bot will handle the verification result.

    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Verifying...</title>
        <style>
            body { font-family: sans-serif; display: flex; flex-direction: column; justify-content: center; align-items: center; height: 100vh; margin: 0; background-color: #f0f2f5; }
            .container { background-color: #ffffff; padding: 40px; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); text-align: center; }
            h1 { color: #333; margin-bottom: 20px; }
            p { color: #666; margin-bottom: 30px; }
            .button { display: inline-block; background-color: #28a745; color: white; padding: 15px 30px; border: none; border-radius: 5px; cursor: pointer; font-size: 1.1em; text-decoration: none; transition: background-color 0.3s ease; }
            .button:hover { background-color: #218838; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Verification Complete</h1>
            <p>Click the button below to open Telegram and complete the process.</p>
            <a href="https://telegram.dog/{{ bot_username }}?start=token_{{ token }}" class="button">Open Telegram</a>
        </div>
    </body>
    </html>
    """
    return await render_template_string(html_content, bot_username=BOT_USERNAME, token=token)


if __name__ == "__main__":
    app.run()
