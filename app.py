from quart import Quart, request, render_template_string
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

    if request_id:
        shortener_redirect_url = await get_shortener_link_async(request_id)
        if not shortener_redirect_url:
            return "Invalid ID or link expired.", 404
    else:
        # Fallback for old links or if someone manually tries the old format
        shortener_redirect_url = request.args.get('redirect_to_shortener')
        if not shortener_redirect_url:
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
            .container { background-color: #ffffff; padding: 40px; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); text-align: center; }
            h1 { color: #333; margin-bottom: 20px; }
            p { color: #666; margin-bottom: 30px; }
            .button { background-color: #007bff; color: white; padding: 15px 30px; border: none; border-radius: 5px; cursor: pointer; font-size: 1.1em; text-decoration: none; transition: background-color 0.3s ease; }
            .button:hover { background-color: #0056b3; }
        </style>
        <script>
            function goToLink() {
                var url = {{ url|tojson }};
                window.location.href = url;
            }
        </script>
    </head>
    <body>
        <div class="container">
            <h1>Human Verification</h1>
            <p>Click below to proceed to the token verification process. This helps us ensure you are not a bot.</p>
            <button onclick="goToLink()" class="button">Click Here to Proceed</button>
        </div>
    </body>
    </html>
    """
    return await render_template_string(html_content, url=shortener_redirect_url)


if __name__ == "__main__":
    app.run()
