# opencode Integration Guide

This guide explains how to configure [opencode](https://opencode.ai) to use Dedalus Labs models through this proxy.

## Tested Models

The following models have been verified to work with opencode:

| Model | Status |
|-------|--------|
| `anthropic/claude-opus-4-5` | Working |
| `openai/gpt-5.2` | Working |
| `google/gemini-3-pro-preview` | Partial - [known issues with multi-turn tool calling](GOOGLE_TOOL_CALLING_BUG.md) |

Other models may or may not work.

## Quick Setup

1. **Start the proxy server**

   ```bash
   export DEDALUS_API_KEY=your-api-key
   dedalus-proxy --host 0.0.0.0
   ```

2. **Configure opencode**

   Create or edit your `opencode.json` configuration file:

   ```json
   {
     "provider": {
       "dedalus-labs": {
         "npm": "@ai-sdk/openai-compatible",
         "name": "dedalus-labs",
         "options": {
           "name": "dedalus-labs",
           "baseURL": "http://localhost:8000/v1"
         },
         "models": {
           "openai/gpt-5.2": {
             "name": "GPT-5.2",
             "variants": {
               "xhigh": {
                 "reasoningEffort": "xhigh",
                 "textVerbosity": "low"
               },
               "high": {
                 "reasoningEffort": "high",
                 "textVerbosity": "low"
               },
               "medium": {
                 "reasoningEffort": "medium",
                 "textVerbosity": "low"
               },
               "low": {
                 "reasoningEffort": "low",
                 "textVerbosity": "low"
               }
             }
           },
           "anthropic/claude-opus-4-5": {
             "name": "Claude Opus 4.5"
           }
         }
       }
     }
   }
   ```

3. **Run opencode**

   The proxy handles all OpenAI-compatible requests and forwards them to Dedalus Labs.

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DEDALUS_API_KEY` | Yes | Your Dedalus Labs API key (for the proxy) |
| `OPENAI_API_KEY` | Yes* | Required by opencode/client (can be any dummy value like `dummy`); the proxy ignores it |

*opencode requires an API key environment variable to be set, even though the proxy doesn't use it.

## Model Names

Pass model names directly as expected by the Dedalus Labs API. Examples:

| Model | Provider |
|-------|----------|
| `openai/gpt-5.2` | OpenAI |
| `openai/gpt-4.1` | OpenAI |
| `openai/gpt-4o` | OpenAI |
| `anthropic/claude-opus-4-5` | Anthropic |
| `anthropic/claude-sonnet-4-5` | Anthropic |
| `google/gemini-3-pro-preview` | Google |
| `google/gemini-2.5-pro` | Google |

See Dedalus Labs documentation for the full list of available models.

## Troubleshooting

### Connection Refused

**Symptom**: `Connection refused` error when opencode tries to connect.

**Solution**: Ensure the proxy is running:

```bash
curl http://localhost:8000/health
# Should return: {"status":"ok"}
```

If using Docker, check the container is running:

```bash
docker ps | grep dedalus-proxy
```

### Authentication Error

**Symptom**: `Invalid API key` or `401 Unauthorized` error.

**Solution**: Verify your `DEDALUS_API_KEY` is set correctly:

```bash
# Check if the variable is set
echo $DEDALUS_API_KEY

# Restart the proxy with the correct key
export DEDALUS_API_KEY=your-actual-api-key
dedalus-proxy
```

### Model Not Found

**Symptom**: Error about invalid or unavailable model.

**Solution**: Use the full Dedalus model path (e.g., `openai/gpt-4o`). See the Dedalus Labs documentation for available models.

### Slow Responses

**Symptom**: Requests take a long time to complete.

**Solution**: 

1. Enable streaming for faster perceived response time:
   ```json
   {
     "stream": true
   }
   ```

2. Check your network connection to Dedalus Labs API.

3. Try a faster model like `openai/gpt-5-mini` or `anthropic/claude-haiku-4-5`.

### Large File Writes Failing or Stalling

**Symptom**: When asking the model to write large files, the response gets stuck or the connection drops.

**Solution**: 

The proxy includes automatic keepalive pings to prevent connection timeouts during long-running responses. If you're still experiencing issues:

1. Increase the keepalive interval if your network has strict timeout requirements:
   ```bash
   STREAM_KEEPALIVE_INTERVAL=10 dedalus-proxy
   ```
   The default is 15 seconds. Lower values send more frequent pings.

2. If using a reverse proxy (nginx, Cloudflare, etc.), ensure buffering is disabled. The proxy sends `X-Accel-Buffering: no` header, but you may need additional configuration.

3. Check if your client or intermediate proxies have connection timeout settings that need adjustment.

### Viewing Logs

Enable debug logging to see detailed request/response information:

```bash
dedalus-proxy --log-level debug
```

For structured JSON logs (useful for log aggregation):

```bash
dedalus-proxy --json-logs
```

## Docker Setup

If running the proxy in Docker:

```bash
docker run -d \
  --name dedalus-proxy \
  -e DEDALUS_API_KEY=your-api-key \
  -p 8000:8000 \
  dedalus-proxy
```

Then configure opencode to connect to `http://localhost:8000/v1`.

### Network Considerations

If opencode runs in a different container or on a different machine:

- **opencode in Docker on macOS/Windows**: Use `http://host.docker.internal:8000/v1`
- **opencode in Docker on Linux**: Use the host IP address or Docker network service name
- **opencode on another machine**: Use the host machine's IP address instead of `localhost`
