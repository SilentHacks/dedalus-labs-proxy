# Google Models Compatibility

## Status: WORKING ✅

Multi-turn tool calling with Google Gemini 3 models (e.g., `google/gemini-3-pro-preview`) is now fully supported.

## Implementation Details

### Thought Signatures

Google Gemini 3 models require `thought_signature` on function call parts in conversation history. When the client (e.g., OpenCode) doesn't preserve these signatures, the proxy injects Google's approved bypass value to skip validation.

See: https://ai.google.dev/gemini-api/docs/thought-signatures#faqs

### Tool Schema Sanitization

Google's API rejects certain JSON Schema keywords that OpenAI accepts. The proxy automatically sanitizes tool schemas by removing:

- `$schema`
- `additionalProperties`
- Numeric constraints: `maxLength`, `minLength`, `maxItems`, `minItems`, `minimum`, `maximum`, `exclusiveMinimum`, `exclusiveMaximum`, `multipleOf`

### Streaming Limitation

Google models with tools use a non-streaming fallback. The proxy makes a non-streaming API call, then simulates streaming output to the client. This is because the Dedalus API doesn't support true streaming for Google models with function calling.

Keepalive pings are sent during long API calls to prevent connection timeouts.

## Related Files

- `src/dedalus_labs_proxy/routes/chat.py` - Main chat endpoint with Google-specific handling:
  - `_inject_thought_signatures()` - Injects bypass signatures for Gemini 3
  - `_sanitize_tools_for_google()` - Removes incompatible schema fields
  - `_stream_google_with_tools()` - Non-streaming fallback with simulated streaming
