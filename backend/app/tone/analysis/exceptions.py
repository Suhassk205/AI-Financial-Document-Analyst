"""Custom exceptions for management tone analysis (Phase 5)."""


class ToneAnalysisError(Exception):
    """Base exception for all tone analysis failures."""


class ToneLLMError(ToneAnalysisError):
    """Failed to query the LLM successfully (generic)."""


class ToneLLMTransientError(ToneLLMError):
    """Transient network or rate limit failure from the LLM, safe to retry."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.retryable = True


class ToneLLMResponseError(ToneAnalysisError):
    """The LLM returned a response, but it was malformed or violates the schema."""
