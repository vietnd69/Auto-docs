"""JSON schemas for Ollama structured output (format parameter)."""

REVIEW_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "approved": {"type": "boolean"},
        "need_special_case": {"type": "boolean"},
        "special_case_reason": {"type": "string"},
        "special_case_standard_heading": {"type": "string"},
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

JURY_VOTE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "vote": {"type": "string", "enum": ["yes", "no"]},
        "reason": {"type": "string"},
    },
    "required": ["vote", "reason"],
}

PATCHES_SCHEMA: dict = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "old_text": {"type": "string"},
            "new_text": {"type": "string"},
            "reason": {"type": "string"},
            "allow_drops": {"type": "boolean"},
        },
        "required": ["old_text", "new_text", "reason"],
    },
}

# ── Typed schemas for chunked validator (replaces REVIEW_SCHEMA / PATCHES_SCHEMA in chunked path) ──

FINDINGS_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "approved": {"type": "boolean"},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "section":   {"type": "string"},
                    "function":  {"type": ["string", "null"]},
                    "field":     {"type": ["string", "null"]},
                    "rule_id":   {"type": "string"},
                    "issue":     {"type": "string"},
                },
                "required": ["section", "rule_id", "issue"],
            },
        },
    },
    "required": ["approved", "findings"],
}

TYPED_OP_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "op":       {"type": "string",
                     "enum": ["update_section", "update_field", "rewrite_function", "delete_function"]},
        "section":  {"type": "string"},
        "function": {"type": ["string", "null"]},
        "field":    {"type": ["string", "null"]},
        "value":    {"type": ["string", "null"]},
        "content":  {"type": ["string", "null"]},
    },
    "required": ["op", "section"],
}

_TYPED_OP_ITEM: dict = {
    "type": "object",
    "properties": {
        "op":       {"type": "string",
                     "enum": ["update_section", "update_field", "rewrite_function", "delete_function"]},
        "section":  {"type": "string"},
        "function": {"type": ["string", "null"]},
        "field":    {"type": ["string", "null"]},
        "value":    {"type": ["string", "null"]},
        "content":  {"type": ["string", "null"]},
    },
    "required": ["op", "section"],
}

TYPED_OPS_LIST_SCHEMA: dict = {
    "type": "array",
    "items": _TYPED_OP_ITEM,
}
