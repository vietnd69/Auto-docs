"""Regex-driven Lua 5.1 lexer: comments dropped, strings kept as values, 1-based lines."""

from __future__ import annotations

import bisect
import re
from collections.abc import Iterator
from dataclasses import dataclass

KEYWORDS = frozenset(
    {
        "and",
        "break",
        "do",
        "else",
        "elseif",
        "end",
        "false",
        "for",
        "function",
        "goto",
        "if",
        "in",
        "local",
        "nil",
        "not",
        "or",
        "repeat",
        "return",
        "then",
        "true",
        "until",
        "while",
    }
)

_TOKEN_RE = re.compile(
    r"""
    (?P<lcomment>--\[(?P<ceq>=*)\[.*?\](?P=ceq)\])
  | (?P<comment>--[^\n]*)
  | (?P<lstring>\[(?P<seq>=*)\[.*?\](?P=seq)\])
  | (?P<dstring>"(?:\\[\s\S]|[^"\\\n])*")
  | (?P<sstring>'(?:\\[\s\S]|[^'\\\n])*')
  | (?P<number>0[xX][0-9a-fA-F.]+(?:[pP][+-]?\d+)?|\d+\.?\d*(?:[eE][+-]?\d+)?|\.\d+(?:[eE][+-]?\d+)?)
  | (?P<name>[A-Za-z_]\w*)
  | (?P<punct>\.\.\.|\.\.|==|~=|<=|>=|::|//|[-+*/%^\#&~|<>=(){}\[\];:,.])
  | (?P<space>\s+)
  | (?P<other>.)
    """,
    re.VERBOSE | re.DOTALL,
)


@dataclass(frozen=True, slots=True)
class Token:
    kind: str  # "name", "keyword", "string", "number", "punct"
    value: str
    line: int


def _unquote(raw: str, group: str) -> str:
    if group == "lstring":
        start = raw.index("[", 1) + 1
        return raw[start : len(raw) - (start)]
    return raw[1:-1]


def tokenize(source: str) -> Iterator[Token]:
    """Yield significant tokens of ``source`` with their starting line number."""
    newlines = [i for i, ch in enumerate(source) if ch == "\n"]
    for match in _TOKEN_RE.finditer(source):
        group = match.lastgroup
        if group in ("space", "comment", "lcomment", "other", None):
            continue
        line = bisect.bisect_right(newlines, match.start() - 1) + 1
        raw = match.group(group)
        if group in ("lstring", "dstring", "sstring"):
            yield Token("string", _unquote(raw, group), line)
        elif group == "name":
            yield Token("keyword" if raw in KEYWORDS else "name", raw, line)
        else:
            yield Token(group, raw, line)
