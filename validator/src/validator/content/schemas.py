"""JSON schemas for Ollama structured output (format parameter)."""

REVIEW_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "approved": {"type": "boolean"},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "issue": {"type": "string"},
                    "suggestion": {"type": "string"},
                },
                "required": ["issue", "suggestion"],
            },
        },
    },
    "required": ["approved", "findings"],
}

PATCHES_SCHEMA: dict = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "old_text": {"type": "string"},
            "new_text": {"type": "string"},
            "reason": {"type": "string"},
        },
        "required": ["old_text", "new_text", "reason"],
    },
}
