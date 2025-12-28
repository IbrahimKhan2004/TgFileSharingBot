from quart import Quart, request, render_template_string, redirect
import os
import urllib.parse
import base64
from database import get_shortener_link_async

app = Quart(__name__)

@app.route('/')
async def hello_world():
    return '⚡Your App is Running⚡'

@app.route('/gate')
async def human_gate():
    request_id = request.args.get('id')

    # We just need to check for the ID and pass it to the template.
    if not request_id:
        return "Invalid request. Missing ID.", 400

    # Fetch the destination URL here to encode it
    shortener_redirect_url = await get_shortener_link_async(request_id)
    if not shortener_redirect_url:
        return "Invalid ID or link expired.", 404

    # Encode the URL to hide it from source
    encoded_url = base64.b64encode(shortener_redirect_url.encode('utf-8')).decode('utf-8')

    html_content = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>SecureLink Verification</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">

  <style>
    body {
      margin: 0;
      min-height: 100vh;
      background: linear-gradient(135deg, #7c3aed, #2563eb);
      font-family: system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
      display: flex;
      align-items: center;
      justify-content: center;
    }

    .container {
      width: 100%;
      padding: 16px;
    }

    .card {
      max-width: 360px;
      margin: auto;
      background: #ffffff;
      padding: 28px 24px;
      border-radius: 16px;
      box-shadow: 0 15px 40px rgba(0, 0, 0, 0.15);
      text-align: center;
      animation: fadeIn 0.6s ease;
    }

    .warning-container {
      background-color: #fff3cd;
      color: #856404;
      border: 1px solid #ffeeba;
    }

    h1, h2 {
      margin: 0;
      color: #111827;
    }

    h1 { font-size: 26px; }
    h2 { font-size: 22px; }

    p {
      margin: 8px 0 20px;
      font-size: 14px;
      color: #6b7280;
    }

    /* Loader */
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
      0% { width: 0 }
      100% { width: 100% }
    }

    /* Captcha box */
    .captcha-box {
      margin: 20px 0;
      padding: 18px;
      border: 1px solid #e5e7eb;
      border-radius: 10px;
      font-size: 14px;
      color: #374151;
    }

    button {
      width: 100%;
      padding: 14px;
      border-radius: 999px;
      background: #2563eb;
      color: #ffffff;
      border: none;
      font-size: 16px;
      font-weight: 600;
      cursor: not-allowed;
      opacity: 0.6;
      transition: 0.3s;
    }

    button.enabled {
      cursor: pointer;
      opacity: 1;
    }

    button.enabled:hover {
      background: #1d4ed8;
    }

    small {
      display: block;
      margin-top: 14px;
      font-size: 12px;
      color: #6b7280;
    }

    .hide {
      display: none;
    }

    @keyframes fadeIn {
      from {
        opacity: 0;
        transform: translateY(20px);
      }
      to {
        opacity: 1;
        transform: translateY(0);
      }
    }
  </style>
</head>

<body>

<div class="container">
  <div class="card" id="main-card" style="display:none;">

    <!-- STEP 1: LOADING -->
    <div id="loading">
      <h2>Checking Security</h2>
      <p>Please wait…</p>
      <div class="loader"><span></span></div>
    </div>

    <!-- STEP 2: VERIFICATION -->
    <div id="captcha" class="hide">
      <h1>SecureLink</h1>
      <p>Security Verification Required</p>

      <div class="captcha-box">
        ⬜ I'm not a robot
      </div>

      <button id="continueBtn">Continue</button>
      <small>🔒 Your connection is secure</small>
    </div>

  </div>

  <div id="warning-container" class="card warning-container" style="display:none;">
      <h2>Browser Check Failed</h2>
      <p>Please open this link in <b>Google Chrome</b> to proceed.</p>
      <p>Kripya is link ko Google Chrome me khole.</p>
  </div>
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
        document.getElementById('main-card').style.display = 'block';
        document.getElementById('warning-container').style.display = 'none';

        // Start the 3-second timer only if browser check passes
        setTimeout(() => {
            document.getElementById("loading").style.display = "none";
            document.getElementById("captcha").classList.remove("hide");
            document.getElementById("continueBtn").classList.add("enabled");

            // Add click listener
            document.getElementById("continueBtn").onclick = function() {
                if(this.classList.contains('enabled')) {
                   const encoded = "{{ encoded_url }}";
                   const decoded = atob(encoded);
                   window.location.href = decoded;
                }
            };
        }, 3000);
    }

    function showWarning() {
        document.getElementById('main-card').style.display = 'none';
        document.getElementById('warning-container').style.display = 'block';
    }

    checkBrowser();
</script>

</body>
</html>
    """
    return await render_template_string(html_content, encoded_url=encoded_url)


@app.route('/verify/<request_id>')
async def verify_redirect(request_id):
    """
    Legacy endpoint.
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
