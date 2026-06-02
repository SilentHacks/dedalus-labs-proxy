"""Known model context window sizes."""

DEFAULT_CONTEXT_LIMITS: dict[str, int] = {
    "openai/gpt-4o": 128_000,
    "openai/gpt-4.1": 1_047_576,
    "openai/gpt-5.2": 400_000,
    "anthropic/claude-opus-4-5": 200_000,
    "anthropic/claude-sonnet-4-5": 200_000,
    "google/gemini-3-pro-preview": 1_000_000,
    "google/gemini-3-flash-preview": 1_000_000,
}


def build_context_limits(overrides: dict[str, int] | None = None) -> dict[str, int]:
    """Return merged static and override context limits."""
    limits = dict(DEFAULT_CONTEXT_LIMITS)
    if overrides:
        limits.update(overrides)
    return limits


def get_context_window(model: str, limits: dict[str, int]) -> int | None:
    """Look up context window for a model, if known."""
    return limits.get(model)
