// Cloudflare Worker Script for Streaming Telegram Files
// This script acts as a secure and efficient bridge between the user and Telegram's file servers.
// It handles HTTP Range Requests to stream large files without hitting memory limits.

addEventListener('fetch', event => {
  event.respondWith(handleRequest(event.request));
});

async function handleRequest(request) {
  const url = new URL(request.url);
  const pathParts = url.pathname.split('/');

  // We expect a URL format like /download/<encrypted_data>
  if (pathParts.length !== 3 || pathParts[1] !== 'download' || !pathParts[2]) {
    return new Response('Invalid URL format. Expected /download/<encrypted_data>', { status: 400 });
  }

  const encryptedData = pathParts[2];

  try {
    // Phase 1: Get File Metadata from our own backend
    // The worker calls our bot's web server to get the actual Telegram file URL.
    // This is a security measure to avoid exposing Telegram links directly and to control access.
    // 'BACKEND_URL' and 'WORKER_SECRET' must be set as secrets in the Cloudflare Worker dashboard.
    const backendResponse = await fetch(`${BACKEND_URL}/api/get_file_info`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Worker-Secret': WORKER_SECRET, // Secret to authenticate the worker to the backend
      },
      body: JSON.stringify({ encrypted_data: encryptedData }),
    });

    if (!backendResponse.ok) {
      const errorText = await backendResponse.text();
      return new Response(`Failed to get file info from backend: ${errorText}`, { status: backendResponse.status });
    }

    const fileInfo = await backendResponse.json();
    const telegramFileUrl = new URL(fileInfo.file_url);

    // Phase 2: Stream the File from Telegram to the User
    // The real magic happens here. The worker fetches the file from Telegram,
    // respecting the Range header from the user's browser, and streams it back.
    const range = request.headers.get('range');

    const headers = new Headers();
    if (range) {
      headers.set('range', range);
    }

    // Add other headers from the original request that might be useful
    // for caching or content negotiation, but be careful not to leak sensitive info.
    if (request.headers.has('accept')) headers.set('accept', request.headers.get('accept'));
    if (request.headers.has('accept-language')) headers.set('accept-language', request.headers.get('accept-language'));

    const telegramResponse = await fetch(telegramFileUrl.toString(), {
      method: 'GET',
      headers: headers,
    });

    // Create a new response that is streamable
    const responseHeaders = new Headers(telegramResponse.headers);
    responseHeaders.set('Access-Control-Allow-Origin', '*'); // Allow cross-origin requests
    responseHeaders.set('Content-Disposition', `attachment; filename="${fileInfo.file_name}"`);

    // Ensure browsers can seek and see the total file size
    responseHeaders.set('Accept-Ranges', 'bytes');

    // For a 206 Partial Content response, the status code must be 206.
    const responseStatus = telegramResponse.status === 206 ? 206 : 200;

    return new Response(telegramResponse.body, {
      status: responseStatus,
      headers: responseHeaders,
    });

  } catch (error) {
    console.error('Worker Error:', error);
    return new Response('An internal error occurred in the worker.', { status: 500 });
  }
}
