from flask import Flask, redirect, request, render_template_string # Modified: Added render_template_string
import os
import urllib.parse # Added: For URL encoding/decoding

app = Flask(__name__)

@app.route('/')
def hello_world():
    return '⚡Your App is Running⚡'

@app.route('/gate') # Added: New route for human gate
def human_gate(): # Added: New function for human gate
    # 'redirect_to_shortener' parameter mein actual shortened URL hogi
    shortener_redirect_url = request.args.get('redirect_to_shortener') 

    if not shortener_redirect_url:
        return "Invalid request. Missing redirect URL.", 400

    # Ye ek simple HTML page hai jisme ek button hai
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Verifikasi Manusia</title>
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
            <h1>Verifikasi Manusia</h1>
            <p>Klik di bawah untuk melanjutkan ke proses verifikasi token.</p>
            <a href="{shortener_redirect_url}" class="button">Klik di Sini untuk Melanjutkan</a>
        </div>
    </body>
    </html>
    """
    return render_template_string(html_content)


if __name__ == "__main__":
    app.run()
