from quart import Quart, request, render_template_string, redirect
import os
import urllib.parse
from database import get_shortener_link_async

app = Quart(__name__)

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
                var userAgent = navigator.userAgent;
                var vendor = navigator.vendor;
                var isChrome = false;

                // Desktop/Android Chrome check
                if (/Chrome/.test(userAgent) && /Google Inc/.test(vendor)) {
                    isChrome = true;
                }
                // iOS Chrome check
                if (/CriOS/.test(userAgent)) {
                    isChrome = true;
                }

                // Exclude Edge
                if (/Edg/.test(userAgent)) {
                    isChrome = false;
                }
                // Exclude Opera
                if (/OPR/.test(userAgent)) {
                    isChrome = false;
                }

                // Exclude Brave
                if (navigator.brave && await navigator.brave.isBrave()) {
                    isChrome = false;
                }

                if (isChrome) {
                    document.getElementById('main-container').style.display = 'block';
                } else {
                    document.getElementById('warning-container').style.display = 'block';
                }
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


if __name__ == "__main__":
    app.run()
