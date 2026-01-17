# Google Models Tool Calling Bug

## Status

This issue affects `google/gemini-3-pro-preview` and other Google models when used with opencode or other agentic tools that require multi-turn tool calling.

## Summary

**Multi-turn tool calling conversations with Google models (e.g., `google/gemini-3-pro-preview`) are broken** when using the Dedalus SDK/API. The first tool call works, but subsequent turns that include tool call history in the messages fail with a validation error.

## Symptoms

When sending a request with tool call history (messages containing `tool_calls` from the assistant or `role: tool` responses), the Dedalus API returns:

```json
{
  "detail": {
    "error": {
      "message": "Invalid request format: 1 validation error for GenerateContentRequest\ncontents.1.parts.0.functionCall.arguments\n  Field required [type=missing, input_value={'name': 'bash', 'args': ...}, input_type=dict]",
      "type": "validation_error"
    }
  }
}
```

## Root Cause

The bug is in the Dedalus SDK/API's transformation layer when converting OpenAI-format requests to Google's native format:

1. **OpenAI format** uses `function.arguments` as a JSON **string**:
   ```json
   {
     "tool_calls": [{
       "function": {
         "name": "bash",
         "arguments": "{\"command\": \"ls\"}"
       }
     }]
   }
   ```

2. **Google's native format** uses `functionCall.args` as a **dict**:
   ```json
   {
     "functionCall": {
       "name": "bash",
       "args": {"command": "ls"}
     }
   }
   ```

3. **The Dedalus SDK bug**: When transforming OpenAI format to Google format, the SDK:
   - Correctly parses the `arguments` JSON string into a dict
   - **Incorrectly** names the field `args` instead of `arguments`
   - Google's API expects `arguments` (as a dict), not `args`

The result: Google receives `{'name': 'bash', 'args': {...}}` but expects `{'name': 'bash', 'arguments': {...}}`.

## What Works

- Initial requests with tools (no tool call history) work fine
- Text-only conversations work fine
- Streaming without tools works fine

## What Doesn't Work

- Any request containing previous tool calls in the message history
- Multi-turn agentic workflows with Google models

## Attempted Workarounds

We attempted several workarounds, none of which succeeded:

### 1. Send `arguments` as JSON string
**Approach**: Keep `arguments` as a JSON string (OpenAI format).
**Result**: Dedalus API validation rejects it with HTTP 422 - expects `arguments` to be a string but receives a dict after their transformation.

### 2. Send `arguments` as dict
**Approach**: Send `arguments` as a dict directly, hoping it passes through.
**Result**: Dedalus still renames `arguments` to `args`, Google still fails.

### 3. Send both `arguments` AND `args`
**Approach**: Include both fields hoping one survives the transformation.
**Result**: Dedalus transforms `arguments` to `args`, resulting in duplicate `args` fields. Google still doesn't receive `arguments`.

### 4. Direct Google API call
**Approach**: Bypass Dedalus's OpenAI-compatible endpoint and call Google's native API format directly via a passthrough endpoint.
**Result**: The passthrough endpoint (`/google/v1beta/models/{model}:generateContent`) returns 404 - it doesn't exist on the Dedalus API.

### 5. Convert to Google native format ourselves
**Approach**: Transform messages to Google's `contents` format with `functionCall`/`functionResponse` parts.
**Result**: Same 404 - no passthrough endpoint available.

## Current Behavior

The proxy now:
1. Logs a warning when tool call history is detected for Google models
2. Attempts the request anyway (which will fail)
3. Returns the error to the client

```
WARNING: Tool call history detected for Google model. This is a known limitation - 
multi-turn tool conversations fail due to a bug in the Dedalus SDK.
```

## Recommendations

### For Users
- **Use non-Google models** (e.g., Anthropic Claude, OpenAI) for agentic/tool-calling workflows
- Google models work fine for:
  - Single-turn tool calls (one request, one tool response)
  - Text-only conversations
  - Streaming without tools

### For Dedalus Labs
The fix needs to happen in the Dedalus SDK/API. The transformation from OpenAI format to Google format should:
- Parse `function.arguments` (JSON string) into a dict
- Name the resulting field `arguments`, **not** `args`

Example correct transformation:
```python
# OpenAI format input
{"function": {"name": "bash", "arguments": "{\"command\": \"ls\"}"}}

# Should become (for Google)
{"functionCall": {"name": "bash", "arguments": {"command": "ls"}}}

# NOT
{"functionCall": {"name": "bash", "args": {"command": "ls"}}}  # WRONG
```

## Code References

- Warning logged in: `src/dedalus_labs_proxy/routes/chat.py` (see `_stream_google_with_tools` and `chat_completions`)
- Helper function: `_has_tool_call_history()` detects affected requests

## Related Files

- `src/dedalus_labs_proxy/routes/chat.py` - Main chat endpoint with workaround code
- `docs/GOOGLE_TOOL_CALLING_BUG.md` - This document
