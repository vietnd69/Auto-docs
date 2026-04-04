"""Jury role: 5 LLM votes to accept or reject a format special case requested by reviewer.

When the reviewer signals need_special_case=true, this module runs JURY_SIZE LLM calls.
If votes_yes >= JURY_MIN_YES (i.e. 4 or 5 out of 5), the special case is accepted and
format heading checks are bypassed for this file.
"""

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from llm.client import ollama_chat
from llm.paths import PROJECT_ROOT
from llm.settings import BAD_RESPONSE_RETRIES, DEBUG_PROMPTS, MODEL_JURY, NORMAL_SLEEP
from llm.tokens import count_tokens
from validator.content.prompts import build_jury_prompt

_DEBUG_DIR = PROJECT_ROOT / ".cache" / "debug_prompts"


def _dump_prompt(label: str, text: str) -> None:
    _DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    path = _DEBUG_DIR / f"{label}_{ts}.txt"
    path.write_text(text, encoding="utf-8")
    print(f"  [debug] Prompt dumped → {path}")


JURY_SIZE = 5
JURY_MIN_YES = 4  # minimum YES votes required to accept (out of JURY_SIZE=5)


@dataclass
class JuryVerdict:
    """Result of the jury vote."""
    accepted: bool          # True if votes_yes >= JURY_MIN_YES
    votes_yes: int
    votes_total: int        # always JURY_SIZE
    reasons: list[str] = field(default_factory=list)


def _vote_once(messages: list[dict], model: str, vote_index: int = 0) -> tuple[bool, str]:
    """Call one LLM jury member. Returns (vote_yes, reason)."""
    for attempt in range(BAD_RESPONSE_RETRIES + 1):
        try:
            response = ollama_chat(model=model, messages=messages)
        except Exception as e:
            if attempt < BAD_RESPONSE_RETRIES:
                continue
            return False, f"API error: {e}"
        raw = response["message"]["content"]
        if DEBUG_PROMPTS:
            _dump_prompt(f"jury_response_v{vote_index}", raw)
        cleaned = re.sub(r'^```(?:json)?\s*\n?', '', raw.strip())
        cleaned = re.sub(r'\n?```\s*$', '', cleaned)
        cleaned = re.sub(r'<think>[\s\S]*?</think>', '', cleaned).strip()
        try:
            data = json.loads(cleaned)
            vote = str(data.get("vote", "no")).lower().strip()
            reason = str(data.get("reason", ""))
            return vote == "yes", reason
        except (json.JSONDecodeError, TypeError):
            if attempt < BAD_RESPONSE_RETRIES:
                continue
    return False, "Failed to parse jury response"


def run_jury(
    md_content: str,
    lua_source: str,
    connected_content: str,
    special_case_reason: str,
    model: str = MODEL_JURY,
) -> JuryVerdict:
    """Run JURY_SIZE LLM votes on whether to accept a format special case.

    Returns JuryVerdict with accepted=True if votes_yes >= JURY_MIN_YES.
    """
    system_prompt, user_content = build_jury_prompt(md_content, lua_source, connected_content, special_case_reason)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    token_count = count_tokens(system_prompt + user_content)
    print(f"  [jury] Prompt: {token_count:,} tokens — running {JURY_SIZE} votes (need >={JURY_MIN_YES})")
    if DEBUG_PROMPTS:
        _dump_prompt("jury_prompt", system_prompt + "\n\n" + user_content)

    votes_yes = 0
    reasons: list[str] = []

    for i in range(JURY_SIZE):
        print(f"  [jury] Vote {i + 1}/{JURY_SIZE}...")
        yes, reason = _vote_once(messages, model, vote_index=i + 1)
        if yes:
            votes_yes += 1
        label = "YES" if yes else "NO"
        reasons.append(f"{label}: {reason}")
        print(f"  [jury]   -> {label}: {reason[:80]}")
        if i < JURY_SIZE - 1:
            time.sleep(NORMAL_SLEEP)

    accepted = votes_yes >= JURY_MIN_YES
    verdict_str = "ACCEPTED" if accepted else "REJECTED"
    print(f"  [jury] Verdict: {verdict_str} ({votes_yes}/{JURY_SIZE} yes)")

    return JuryVerdict(
        accepted=accepted,
        votes_yes=votes_yes,
        votes_total=JURY_SIZE,
        reasons=reasons,
    )
