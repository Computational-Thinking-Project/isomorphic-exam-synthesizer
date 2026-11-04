"""System constants for Isomorphic Exam Synthesizer."""

# Maximum Gemini API calls reserved per single question reject request (1 initial + max 2 math retries)
MAX_AI_CALLS_PER_REJECT: int = 4

# Absolute upper limit of Gemini API calls allowed per exam review session
MAX_SESSION_REVIEW_QUOTA: int = 30

# Timeout duration before a question stuck in 'regenerating' is considered stale and recovered
STALE_REGENERATION_TIMEOUT_SECONDS: int = 180  # 3 minutes
