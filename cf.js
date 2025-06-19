/**
 * Cloudflare Worker for CodeGeeX OpenAI API Adapter
 *
 * @version 1.0.0
 * @description This worker adapts CodeGeeX's API to be compatible with the OpenAI Chat Completions API.
 * It handles client authentication, CodeGeeX token rotation, and transforms streaming/non-streaming responses.
 *
 * @deployment
 * 1. Save this code as a single .js file (e.g., worker.js).
 * 2. Create a new Cloudflare Worker and paste this code.
 * 3. Configure the following environment variables (secrets) in your Worker's settings:
 *    - `CLIENT_API_KEYS`: A JSON string array of valid client API keys. Example: `["sk-abc", "sk-def"]`
 *    - `CODEGEEX_TOKENS`: A comma-separated string of your CodeGeeX tokens. Example: `token1,token2`
 *    - `DEBUG_MODE` (optional): Set to "true" to enable verbose logging for debugging.
 */

// --- Global State & Configuration ---

// State is initialized once on the first request to a new worker instance.
// NOTE: In a multi-instance serverless environment, this state is not shared across instances.
// For robust, distributed state, consider using Cloudflare KV.
let IS_INITIALIZED = false;
let VALID_CLIENT_KEYS = new Set();
let CODEGEEX_TOKENS = [];
let DEBUG_MODE = false;

// Constants from the original Python implementation
const CODEGEEX_MODELS = ["claude-3-7-sonnet", "claude-sonnet-4"];
const MAX_ERROR_COUNT = 3;
const ERROR_COOLDOWN = 300 * 1000; // 5 minutes in milliseconds

/**
 * Main fetch handler for the worker.
 */
export default {
    async fetch(request, env) {
        if (!IS_INITIALIZED) {
            initializeState(env);
        }

        const url = new URL(request.url);

        // Simple router
        if (url.pathname === "/v1/models" || url.pathname === "/models") {
            return handleModels(request);
        }
        if (url.pathname === "/v1/chat/completions" && request.method === "POST") {
            return handleChatCompletions(request);
        }
        if (url.pathname === "/debug") {
            return handleDebug(url);
        }

        return new Response('Not Found. Available endpoints: /v1/models, /v1/chat/completions', { status: 404 });
    }
};

// --- Initialization ---

/**
 * Initializes state from environment variables.
 * @param {object} env - The worker's environment variables.
 */
function initializeState(env) {
    logDebug("Initializing worker state...");

    // Load Client API Keys
    try {
        const keys = JSON.parse(env.CLIENT_API_KEYS || "[]");
        VALID_CLIENT_KEYS = new Set(keys);
        logDebug(`Successfully loaded ${VALID_CLIENT_KEYS.size} client API keys.`);
    } catch (e) {
        console.error("Fatal: Failed to parse CLIENT_API_KEYS. Client authentication will fail.", e.message);
        VALID_CLIENT_KEYS = new Set();
    }

    // Load CodeGeeX Tokens
    try {
        const tokens = (env.CODEGEEX_TOKENS || "").split(',').filter(Boolean);
        CODEGEEX_TOKENS = tokens.map(token => ({
            token: token.trim(),
            isValid: true,
            lastUsed: 0,
            errorCount: 0,
        }));
        logDebug(`Successfully loaded ${CODEGEEX_TOKENS.length} CodeGeeX tokens.`);
    } catch (e) {
        console.error("Fatal: Failed to parse CODEGEEX_TOKENS. API calls will fail.", e.message);
        CODEGEEX_TOKENS = [];
    }

    DEBUG_MODE = (env.DEBUG_MODE || "false").toLowerCase() === "true";
    logDebug(`Debug mode is ${DEBUG_MODE ? 'enabled' : 'disabled'}.`);

    IS_INITIALIZED = true;
}

// --- Route Handlers ---

/**
 * Handles requests for the models list.
 * @param {Request} request
 */
function handleModels(request) {
    const url = new URL(request.url);
    // /v1/models requires auth, /models is an open endpoint for compatibility
    if (url.pathname === "/v1/models") {
        const authError = authenticateClient(request);
        if (authError) {
            return authError;
        }
    }

    const modelInfos = CODEGEEX_MODELS.map(modelId => ({
        id: modelId,
        object: "model",
        created: Math.floor(Date.now() / 1000),
        owned_by: "anthropic",
    }));

    return jsonResponse({ object: "list", data: modelInfos });
}

/**
 * Handles the main chat completions logic.
 * @param {Request} request
 */
async function handleChatCompletions(request) {
    const authError = authenticateClient(request);
    if (authError) return authError;

    let requestBody;
    try {
        requestBody = await request.json();
    } catch (e) {
        return jsonError("Invalid JSON in request body.", 400);
    }

    const { model, messages, stream = true } = requestBody;

    if (!model || !CODEGEEX_MODELS.includes(model)) {
        return jsonError(`Model '${model}' not found. Available models: ${CODEGEEX_MODELS.join(", ")}`, 404);
    }
    if (!messages || !Array.isArray(messages) || messages.length === 0) {
        return jsonError("The 'messages' field is required and must be a non-empty array.", 400);
    }

    logDebug(`Processing request for model: ${model}`);

    let prompt, history;
    try {
        ({ prompt, history } = convertMessagesToCodegeexFormat(messages));
    } catch (e) {
        return jsonError(`Failed to process messages: ${e.message}`, 400);
    }

    // Attempt to call CodeGeeX API with token rotation
    const maxAttempts = CODEGEEX_TOKENS.length || 1;
    for (let attempt = 0; attempt < maxAttempts; attempt++) {
        const token = getBestCodegeexToken();
        if (!token) {
            return jsonError("No valid CodeGeeX tokens available.", 503);
        }

        const payload = {
            user_role: 0,
            ide: "VSCode",
            ide_version: "",
            plugin_version: "",
            prompt,
            machineId: "",
            talkId: crypto.randomUUID(),
            locale: "",
            model,
            agent: null,
            candidates: {
                candidate_msg_id: "",
                candidate_type: "",
                selected_candidate: "",
            },
            history,
        };

        const headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Code/1.100.3 Chrome/132.0.6834.210 Electron/34.5.1 Safari/537.36",
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
            "code-token": token.token,
        };

        try {
            logDebug(`Sending request to CodeGeeX API with token ...${token.token.slice(-4)} (Attempt ${attempt + 1}/${maxAttempts})`);
            const response = await fetch("https://codegeex.cn/prod/code/chatCodeSseV3/chat", {
                method: "POST",
                headers: headers,
                body: JSON.stringify(payload),
                signal: AbortSignal.timeout(300000) // 5 minute timeout
            });

            if (!response.ok) {
                const errorText = await response.text();
                handleTokenError(token, response.status, errorText);
                continue; // Try next token
            }

            // Success, process the response
            if (stream) {
                logDebug("Returning stream response.");
                const { readable, writable } = new TransformStream();
                transformCodegeexStream(response.body, writable, model);
                return new Response(readable, {
                    headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache", "Connection": "keep-alive" }
                });
            } else {
                logDebug("Building non-stream response.");
                return await buildCodegeexNonStreamResponse(response.body, model);
            }

        } catch (error) {
            logDebug(`Request to CodeGeeX failed: ${error.name === 'TimeoutError' ? 'Timeout' : error.message}`);
            token.errorCount++;
        }
    }

    return jsonError("All attempts to contact the CodeGeeX API failed.", 503);
}

/**
 * Handles debug mode toggling.
 * @param {URL} url
 */
function handleDebug(url) {
    const enable = url.searchParams.get('enable');
    if (enable !== null) {
        DEBUG_MODE = enable.toLowerCase() === 'true';
    }
    return jsonResponse({ debug_mode: DEBUG_MODE });
}

// --- Core Logic & Helpers ---

/**
 * Authenticates the client request. Returns a Response object on failure, otherwise null.
 * @param {Request} request
 */
function authenticateClient(request) {
    if (VALID_CLIENT_KEYS.size === 0) {
        return jsonError("Service unavailable: Client API keys not configured on server.", 503);
    }
    const authHeader = request.headers.get("Authorization");
    if (!authHeader || !authHeader.startsWith("Bearer ")) {
        return jsonError("API key required in Authorization header.", 401, { "WWW-Authenticate": "Bearer" });
    }
    const clientKey = authHeader.substring(7);
    if (!VALID_CLIENT_KEYS.has(clientKey)) {
        return jsonError("Invalid client API key.", 403);
    }
    return null; // Success
}

/**
 * Selects the best available CodeGeeX token based on usage, errors, and cooldown.
 */
function getBestCodegeexToken() {
    const now = Date.now();
    let validTokens = CODEGEEX_TOKENS.filter(token =>
        token.isValid && (token.errorCount < MAX_ERROR_COUNT || now - token.lastUsed > ERROR_COOLDOWN)
    );

    if (validTokens.length === 0) {
        logDebug("No valid tokens available after filtering.");
        return null;
    }

    // Reset error count for tokens that have been in cooldown
    for (const token of validTokens) {
        if (token.errorCount >= MAX_ERROR_COUNT && now - token.lastUsed > ERROR_COOLDOWN) {
            token.errorCount = 0;
            logDebug(`Token ...${token.token.slice(-4)} cooldown finished. Error count reset.`);
        }
    }

    // Sort by last used (oldest first) then error count (lowest first)
    validTokens.sort((a, b) => (a.lastUsed - b.lastUsed) || (a.errorCount - b.errorCount));

    const token = validTokens[0];
    token.lastUsed = now;
    return token;
}

/**
 * Updates a token's state after an API error.
 * @param {object} token The token object
 * @param {number} status The HTTP status code
 * @param {string} errorText The error response body
 */
function handleTokenError(token, status, errorText) {
    logDebug(`CodeGeeX API error for token ...${token.token.slice(-4)} (Status: ${status}): ${errorText.slice(0, 100)}`);
    if ([401, 403].includes(status)) {
        token.isValid = false;
        logDebug(`Token ...${token.token.slice(-4)} marked as permanently invalid.`);
    } else if ([429, 500, 502, 503, 504].includes(status)) {
        token.errorCount++;
        logDebug(`Token ...${token.token.slice(-4)} error count incremented to: ${token.errorCount}`);
    }
}


/**
 * Converts OpenAI message format to CodeGeeX prompt/history format.
 * This implementation is robust and ensures the last user message is the prompt.
 * @param {Array<object>} messages
 */
function convertMessagesToCodegeexFormat(messages) {
    const lastUserIndex = messages.findLastIndex(msg => msg.role === 'user');
    if (lastUserIndex === -1) {
        throw new Error("No message with 'role: user' found.");
    }

    const lastUserMessage = messages[lastUserIndex];
    const prompt = typeof lastUserMessage.content === 'string' ? lastUserMessage.content : JSON.stringify(lastUserMessage.content);

    const historyMessages = messages.slice(0, lastUserIndex);
    const history = [];

    for (let i = 0; i < historyMessages.length; i++) {
        if (historyMessages[i].role === 'user' && i + 1 < historyMessages.length && historyMessages[i+1].role === 'assistant') {
            history.push({
                query: typeof historyMessages[i].content === 'string' ? historyMessages[i].content : '',
                answer: typeof historyMessages[i+1].content === 'string' ? historyMessages[i+1].content : '',
                id: crypto.randomUUID()
            });
            i++; // Skip the assistant message we just processed
        }
    }

    logDebug(`Converted messages. Prompt length: ${prompt.length}, History pairs: ${history.length}`);
    return { prompt, history };
}

/**
 * Transforms a CodeGeeX SSE stream to an OpenAI-compatible SSE stream.
 * @param {ReadableStream} inputStream
 * @param {WritableStream} writableStream
 * @param {string} model
 */
async function transformCodegeexStream(inputStream, writableStream, model) {
    const reader = inputStream.getReader();
    const writer = writableStream.getWriter();
    const decoder = new TextDecoder();
    const encoder = new TextEncoder();

    const streamId = `chatcmpl-${crypto.randomUUID().replace(/-/g, '')}`;
    const created = Math.floor(Date.now() / 1000);

    const write = (data) => writer.write(encoder.encode(data));

    try {
        // Send initial role message as required by OpenAI spec
        await write(`data: ${JSON.stringify({ id: streamId, object: "chat.completion.chunk", created, model, choices: [{ index: 0, delta: { role: "assistant" }, finish_reason: null }] })}\n\n`);

        let buffer = "";
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });

            while (buffer.includes("\n\n")) {
                const eventEndIndex = buffer.indexOf("\n\n");
                const eventData = buffer.substring(0, eventEndIndex);
                buffer = buffer.substring(eventEndIndex + 2);

                let eventType, dataJson;
                for (const line of eventData.split("\n")) {
                    if (line.startsWith("event:")) eventType = line.substring(6).trim();
                    else if (line.startsWith("data:")) {
                        try { dataJson = JSON.parse(line.substring(5).trim()); } catch { logDebug(`Ignoring unparsable data line: ${line}`); }
                    }
                }

                if (!eventType || !dataJson) continue;

                if (eventType === "add" && dataJson.text) {
                    const chunk = { id: streamId, object: "chat.completion.chunk", created, model, choices: [{ index: 0, delta: { content: dataJson.text }, finish_reason: null }] };
                    await write(`data: ${JSON.stringify(chunk)}\n\n`);
                } else if (eventType === "finish") {
                    logDebug("Received finish event. Ending stream.");
                    const chunk = { id: streamId, object: "chat.completion.chunk", created, model, choices: [{ index: 0, delta: {}, finish_reason: "stop" }] };
                    await write(`data: ${JSON.stringify(chunk)}\n\n`);
                    await write("data: [DONE]\n\n");
                    return;
                }
            }
        }
    } catch (e) {
        logDebug(`Stream processing error: ${e.message}`);
    } finally {
        logDebug("Stream finished. Closing writer.");
        try {
            await write("data: [DONE]\n\n");
            await writer.close();
        } catch {}
    }
}


/**
 * Builds a non-streaming response by consuming the entire CodeGeeX stream.
 * @param {ReadableStream} inputStream
 * @param {string} model
 */
async function buildCodegeexNonStreamResponse(inputStream, model) {
    const reader = inputStream.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let fullContent = "";

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        while (buffer.includes("\n\n")) {
            const eventEndIndex = buffer.indexOf("\n\n");
            const eventData = buffer.substring(0, eventEndIndex);
            buffer = buffer.substring(eventEndIndex + 2);

            let eventType, dataJson;
            for (const line of eventData.split("\n")) {
                if (line.startsWith("event:")) eventType = line.substring(6).trim();
                else if (line.startsWith("data:")) {
                    try { dataJson = JSON.parse(line.substring(5).trim()); } catch { logDebug(`Ignoring unparsable data line: ${line}`); }
                }
            }

            if (!eventType || !dataJson) continue;

            if (eventType === "add") {
                fullContent += dataJson.text || "";
            } else if (eventType === "finish") {
                // The 'finish' event's text is the final, complete message.
                if (dataJson.text) fullContent = dataJson.text;
                // Once we get finish, we can stop processing and return.
                return createFinalNonStreamResponse(model, fullContent);
            }
        }
    }

    // Fallback in case stream ends without a 'finish' event
    return createFinalNonStreamResponse(model, fullContent);
}

function createFinalNonStreamResponse(model, content) {
    const responsePayload = {
        id: `chatcmpl-${crypto.randomUUID().replace(/-/g, '')}`,
        object: "chat.completion",
        created: Math.floor(Date.now() / 1000),
        model,
        choices: [{
            index: 0,
            message: { role: "assistant", content },
            finish_reason: "stop",
        }],
        usage: { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 } // Usage data is not provided by CodeGeeX
    };
    return jsonResponse(responsePayload);
}

// --- Utility Functions ---

/**
 * Creates a JSON response.
 * @param {object} body
 * @param {number} status
 * @param {object} headers
 */
function jsonResponse(body, status = 200, headers = {}) {
    return new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json", ...headers },
    });
}

/**
 * Creates a JSON error response.
 * @param {string} message
 * @param {number} status
 * @param {object} headers
 */
function jsonError(message, status, headers = {}) {
    return jsonResponse({ error: { message, type: "api_error", code: null } }, status, headers);
}

/**
 * Logs a message if debug mode is enabled.
 * @param {string} message
 */
function logDebug(message) {
    if (DEBUG_MODE) {
        console.log(`[DEBUG] ${new Date().toISOString()} - ${message}`);
    }
}