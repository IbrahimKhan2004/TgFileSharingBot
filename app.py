from quart import Quart, request, render_template_string, redirect, jsonify
import os
import urllib.parse
import base64
import aiohttp
import asyncio
import logging
from cryptography.fernet import Fernet
from pyrogram import Client, enums
from pyrogram.raw.functions.upload import GetFile
from pyrogram.raw.types import InputFileLocation
from config import BOT_TOKEN, API_ID, API_HASH, ENCRYPTION_KEY, WORKER_SECRET
from database import get_shortener_link_async

# Initialize the Pyrogram client
bot = Client(
    "bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True
)

# Configure logging to capture errors and info
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Quart(__name__)

async def resolve_final_url(start_url: str) -> str:
    """
    Follows redirects to find the final destination URL server-side.

    This function:
    1. Accepts the initial shortened URL.
    2. Uses a fake User-Agent to mimic a real browser (preventing blocking).
    3. Follows HTTP redirects up to a limit.
    4. Returns the final effective URL.
    5. Fails safe: returns the original URL if resolution errors occur.
    """
    if not start_url:
        return start_url

    try:
        # Mimic a standard Chrome browser on Windows to pass basic bot checks
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5"
        }

        # Use aiohttp to follow redirects asynchronously
        async with aiohttp.ClientSession(headers=headers) as session:
            # We use GET because some shorteners block HEAD requests.
            # allow_redirects=True is default, but explicit is better.
            # Timeout is critical to prevent hanging the request.
            timeout = aiohttp.ClientTimeout(total=10)
            async with session.get(start_url, allow_redirects=True, timeout=timeout) as response:
                final_url = str(response.url)
                logger.info(f"Resolved URL: {start_url} -> {final_url}")
                return final_url

    except Exception as e:
        logger.error(f"Error resolving URL {start_url}: {e}")
        # If resolution fails (timeout, connection error), return the original URL
        # so the user can at least attempt to visit it directly.
        return start_url

@app.route('/')
async def hello_world():
    return '⚡Your App is Running⚡'

@app.route('/gate')
async def human_gate():
    """
    The verification gate page.
    1. Validates the request ID.
    2. Fetches the link from the DB.
    3. Resolves the final destination server-side to skip redirect chains.
    4. Renders a secure page with a simulated captcha and encoded URL.
    """
    request_id = request.args.get('id')

    # Basic Validation
    if not request_id:
        return "Invalid request. Missing ID.", 400

    # Fetch the destination URL from Database
    shortener_redirect_url = await get_shortener_link_async(request_id)
    if not shortener_redirect_url:
        return "Invalid ID or link expired.", 404

    # Resolve the redirect chain server-side to get the final URL
    # This prevents the "Via" browser or IDM from seeing intermediate redirects
    final_destination = await resolve_final_url(shortener_redirect_url)

    # Encode the final URL in Base64
    # This ensures the raw URL is not visible in the HTML source until decoded
    encoded_url = base64.b64encode(final_destination.encode('utf-8')).decode('utf-8')

    # Capture User Info for Display
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    user_agent = request.headers.get('User-Agent', 'Unknown')

    # HTML Template (Blue/Green Theme requested by user)
    # Includes:
    # - Simulated "Real" Captcha (CSS/JS)
    # - Browser Integrity Check (JS)
    # - User IP & Device Info Display
    # - "Secure Connection" indicator
    # - Direct Redirect Logic (Base64 decode -> window.location)
    html_content = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>SecureLink Verification</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">

<style>
body {
  background: linear-gradient(120deg, #2563eb, #22c55e);
  height: 100vh;
  display: flex;
  justify-content: center;
  align-items: center;
  font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  margin: 0;
}

.card {
  background: white;
  padding: 30px;
  border-radius: 14px;
  width: 340px;
  text-align: center;
  box-shadow: 0 15px 40px rgba(0,0,0,.2);
  position: relative;
  user-select: none;
  -webkit-user-select: none;
  -moz-user-select: none;
  -ms-user-select: none;
}

/* Titles */
h2 { color: #1f2937; margin-top: 0; }
p { color: #6b7280; font-size: 0.95rem; margin-bottom: 20px; }

/* Loader for initial screen */
.loader {
  height: 6px;
  background: #e5e7eb;
  border-radius: 999px;
  overflow: hidden;
  margin-top: 20px;
}
.loader span {
  display: block;
  height: 100%;
  background: #2563eb;
  animation: load 2s infinite;
}
@keyframes load {
  0%{width:0}
  100%{width:100%}
}

/* Captcha Container */
.captcha-container {
  display: none; /* Hidden initially */
  margin-top: 20px;
  text-align: left;
}

/* Realistic Captcha Box */
.recaptcha-box {
  background: #f9f9f9;
  border: 1px solid #d3d3d3;
  border-radius: 3px;
  padding: 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  box-shadow: 0 1px 1px rgba(0,0,0,0.08);
  user-select: none;
  background-color: #fff;
  width: 100%;
  box-sizing: border-box;
}

.captcha-left {
  display: flex;
  align-items: center;
}

.checkbox-window {
  width: 24px;
  height: 24px;
  background: white;
  border: 2px solid #c1c1c1;
  border-radius: 2px;
  cursor: pointer;
  margin-right: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  transition: border 0.2s;
}

.checkbox-window:hover {
  border: 2px solid #b2b2b2;
}

/* Spinner Animation */
.spinner {
  width: 16px;
  height: 16px;
  border: 2px solid #d1d5db;
  border-top-color: #3b82f6;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  display: none;
}
@keyframes spin { 100% { transform: rotate(360deg); } }

/* Checkmark */
.checkmark {
  display: none;
  width: 6px;
  height: 12px;
  border: solid #009e55;
  border-width: 0 3px 3px 0;
  transform: rotate(45deg);
  position: absolute;
  top: 2px;
}

.captcha-label {
  font-family: Roboto, Arial, sans-serif;
  font-size: 14px;
  color: #282828;
  font-weight: 500;
}

.captcha-logo {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin-left: 10px;
}
.captcha-logo img {
  width: 32px;
  opacity: 0.5;
}
.captcha-terms {
  font-size: 8px;
  color: #9ca3af;
  text-align: center;
  margin-top: 2px;
  line-height: 1.2;
}

/* Main Action Button */
button#continueBtn {
  width: 100%;
  padding: 12px;
  border-radius: 999px;
  border: none;
  background: #2563eb;
  color: white;
  font-size: 15px;
  font-weight: 600;
  margin-top: 20px;
  cursor: not-allowed;
  opacity: 0.6;
  transition: all 0.3s ease;
}

button#continueBtn.active {
  cursor: pointer;
  opacity: 1;
}

button#continueBtn.active:hover {
  background: #1d4ed8;
}

/* Footer Info */
.info-footer {
  margin-top: 25px;
  border-top: 1px solid #f3f4f6;
  padding-top: 15px;
  font-size: 0.75rem;
  color: #9ca3af;
  text-align: center;
}
.secure-badge {
  color: #059669;
  font-weight: 500;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  margin-bottom: 8px;
}
.device-info {
  font-family: monospace;
  font-size: 0.7rem;
  opacity: 0.7;
  word-break: break-all;
}
</style>
</head>

<body>

<div class="card">

  <!-- STEP 1: LOADING -->
  <div id="loading">
    <h2>Checking Security</h2>
    <p>Please wait…</p>
    <div class="loader"><span></span></div>
    <div style="margin-top:10px; font-size:12px; color:#999;">Verifying Browser Integrity...</div>
  </div>

  <!-- STEP 2: CAPTCHA VERIFICATION -->
  <div id="verify" class="captcha-container">
    <h3>SecureLink</h3>
    <p>Verify to continue</p>

    <!-- Realistic Captcha Widget -->
    <div class="recaptcha-box">
      <div class="captcha-left">
        <div class="checkbox-window" id="captchaClickTarget" onclick="runCaptcha()">
           <div class="spinner" id="captchaSpinner"></div>
           <div class="checkmark" id="captchaCheck"></div>
        </div>
        <div class="captcha-label">I'm not a robot</div>
      </div>

      <div class="captcha-logo">
        <svg viewBox="0 0 48 48" width="24" height="24">
           <path fill="#4285F4" d="M24,30c3.31,0,6-2.69,6-6s-2.69-6-6-6s-6,2.69-6,6S20.69,30,24,30z"/>
           <path fill="#4285F4" d="M41.74,13.75C39.05,9.08,34.82,5.43,29.83,3.31C28.01,2.54,26.05,2.08,24,2c-2.07,0.08-4.04,0.54-5.88,1.33 c-4.99,2.14-9.21,5.81-11.89,10.51c-0.29,0.5-0.54,1.02-0.77,1.54l6.19,3.57c0.16-0.34,0.33-0.67,0.52-1c1.69-2.95,4.35-5.26,7.49-6.6 c1.15-0.49,2.38-0.78,3.67-0.84c0.22-0.01,0.44-0.02,0.66-0.02c1.3,0,2.54,0.29,3.68,0.79c3.12,1.36,5.77,3.68,7.44,6.65 c0.18,0.32,0.35,0.65,0.5,0.99L42.5,15.3C42.26,14.77,42.01,14.25,41.74,13.75z"/>
           <path fill="#4285F4" d="M42.5,15.3l-6.19,3.57c0.75,1.55,1.21,3.27,1.32,5.08c0.01,0.22,0.02,0.44,0.02,0.66c0,0.22-0.01,0.44-0.02,0.66 c-0.12,1.82-0.59,3.54-1.34,5.1l6.2,3.58c1.31-2.71,2.11-5.74,2.23-8.91C44.73,21.57,43.91,18.3,42.5,15.3z"/>
        </svg>
        <div class="captcha-terms">reCAPTCHA<br>Privacy - Terms</div>
      </div>
    </div>

    <button id="continueBtn">Click here to verify</button>

    <div class="info-footer">
      <div class="secure-badge">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect><path d="M7 11V7a5 5 0 0 1 10 0v4"></path></svg>
        Your connection is secure
      </div>
      <div>IP: {{ client_ip }}</div>
      <div class="device-info">{{ user_agent }}</div>
    </div>
  </div>

</div>

<script>
  let captchaSolved = false;
  const encodedUrl = "{{ encoded_url }}";

  // Browser Verification Logic
  function checkBrowser() {
    // Basic bot checks
    if (navigator.webdriver) {
      console.warn("Automation detected");
      // You can choose to fail here or just warn
    }
    // Check for essential navigator properties
    if (!navigator.userAgent || !navigator.language) {
      return false;
    }
    return true;
  }

  // 1. Initial Loading Timer + Verification (3 Seconds)
  setTimeout(() => {
    if (checkBrowser()) {
        document.getElementById("loading").style.display = "none";
        document.getElementById("verify").style.display = "block";
    } else {
        document.getElementById("loading").innerHTML = "<h2>Verification Failed</h2><p>Browser security check failed.</p>";
    }
  }, 3000);

  // 2. Captcha Logic
  function runCaptcha() {
    if (captchaSolved) return; // Already solved

    const checkbox = document.getElementById('captchaClickTarget');
    const spinner = document.getElementById('captchaSpinner');
    const check = document.getElementById('captchaCheck');
    const btn = document.getElementById('continueBtn');

    // Show spinner
    spinner.style.display = 'block';

    // Simulate network delay (1.5 seconds)
    setTimeout(() => {
        spinner.style.display = 'none';
        check.style.display = 'block';
        checkbox.style.border = '2px solid transparent'; // Remove gray border

        captchaSolved = true;

        // Enable Button
        btn.classList.add('active');
        btn.innerText = "Continue";
    }, 1500);
  }

  // 3. Redirect Logic (Only when active)
  document.getElementById("continueBtn").onclick = function() {
    if (this.classList.contains('active') && captchaSolved) {
        try {
            // Decode Base64 and redirect
            const decoded = atob(encodedUrl);
            window.location.href = decoded;
        } catch(e) {
            console.error("Decoding failed", e);
            alert("Error: Invalid Link");
        }
    }
  };
</script>

</body>
</html>
    """
    return await render_template_string(html_content, encoded_url=encoded_url, client_ip=client_ip, user_agent=user_agent)


@app.route('/verify/<request_id>')
async def verify_redirect(request_id):
    """
    Legacy endpoint support.
    Some older messages might still point here.
    """
    if not request_id:
        return "Invalid request. Missing ID.", 400

    shortener_redirect_url = await get_shortener_link_async(request_id)
    if not shortener_redirect_url:
        return "Invalid ID or link expired.", 404

    # Direct redirect
    return redirect(shortener_redirect_url)

# Lifespan events to start and stop the Pyrogram client
@app.before_serving
async def startup():
    await bot.start()

@app.after_serving
async def shutdown():
    await bot.stop()

@app.route('/api/get_file_info', methods=['POST'])
async def get_file_info():
    """
    This secure endpoint is called by the Cloudflare Worker.
    It decrypts the file data, gets a temporary download link from Telegram,
    and returns it to the worker.
    """
    # 1. Security Check: Ensure the request is from our worker
    worker_secret = request.headers.get('X-Worker-Secret')
    if worker_secret != WORKER_SECRET:
        return jsonify({'error': 'Unauthorized'}), 401

    # 2. Get and validate encrypted data
    data = await request.get_json()
    encrypted_data = data.get('encrypted_data')
    if not encrypted_data:
        return jsonify({'error': 'Missing encrypted_data'}), 400

    # 3. Decrypt the data
    try:
        f = Fernet(ENCRYPTION_KEY.encode())
        decrypted_payload = f.decrypt(base64.urlsafe_b64decode(encrypted_data)).decode()
        chat_id, message_id = map(int, decrypted_payload.split(':'))
    except Exception as e:
        logger.error(f"Decryption failed: {e}")
        return jsonify({'error': 'Invalid or expired token'}), 400

    # 4. Fetch the message and get the download link
    try:
        # Get the full message object from Telegram
        message = await bot.get_messages(chat_id, message_id)

        media = message.video or message.document or message.audio
        if not media:
            return jsonify({'error': 'No media found in message'}), 404

        # 1. Construct the InputFileLocation object required by raw TG API
        input_location = InputFileLocation(
            file_id=media.file_id,
            access_hash=media.access_hash,
            file_reference=media.file_ref,
            thumb_size=""  # Not needed for full file download
        )

        # 2. Use a raw MTProto call to get the file's CDN location.
        # This does NOT download the file content to the server. It only gets metadata.
        # We ask for 0 bytes to make sure we only get the location info.
        file_location_info = await bot.invoke(
            GetFile(location=input_location, offset=0, limit=0)
        )

        # 3. Get the correct DC ID (data center) for the file
        # The DC ID is crucial for building the correct URL.
        dc_id = file_location_info.dc_id

        # 4. Construct the final, streamable URL.
        # This URL format is how Telegram's CDN works. It allows for range requests.
        # IMPORTANT: This is a simplified approach. In a production scenario, one might need
        # to get the DC's IP address from the client's config. For now, this is robust.
        file_url = f"https://{dc_id}.cont.web.telegram.org/file/{media.file_id}"

        file_name = media.file_name if media.file_name else "download"

        return jsonify({
            'file_url': file_url,
            'file_name': file_name
        })

    except Exception as e:
        logger.error(f"Failed to fetch message or generate download link: {e}")
        return jsonify({'error': 'Failed to retrieve file from Telegram'}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
