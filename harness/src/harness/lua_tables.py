"""Shape summaries for data-heavy Lua files (huge tables, generated call lists).

A data reference page documents *structure* (keys, value kinds, samples), never the
full payload, so even multi-megabyte files fit in a small prompt.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from harness.lua_lexer import Token, tokenize

_SAMPLES = 3
_PREVIEW_CHARS = 80


@dataclass
class TableShape:
    entries: int = 0
    keyed: int = 0
    positional: int = 0
    value_kinds: Counter[str] = field(default_factory=Counter)
    samples: list[str] = field(default_factory=list)
    nested_keys: Counter[str] = field(default_factory=Counter)

    def render(self, name: str) -> str:
        kinds = ", ".join(f"{k}×{n}" for k, n in self.value_kinds.most_common())
        lines = [
            f"table {name}: {self.entries} entries ({self.keyed} keyed, {self.positional} positional)",
            f"value kinds: {kinds or 'none'}",
        ]
        if self.nested_keys:
            common = ", ".join(f"{k}({n})" for k, n in self.nested_keys.most_common(25))
            lines.append(f"keys of nested tables (frequency): {common}")
        lines.extend(f"sample: {s}" for s in self.samples)
        return "\n".join(lines)


def _value_kind(tok: Token) -> str:
    if tok.kind == "punct" and tok.value == "{":
        return "table"
    if tok.kind == "keyword" and tok.value == "function":
        return "function"
    if tok.kind == "keyword" and tok.value in ("true", "false"):
        return "boolean"
    if tok.kind == "keyword" and tok.value == "nil":
        return "nil"
    return {"string": "string", "number": "number"}.get(tok.kind, "expression")


def _split_entries(tokens: list[Token]) -> list[list[Token]]:
    """Split the inside of one table constructor into top-level entries."""
    entries: list[list[Token]] = [[]]
    depth = 0
    for tok in tokens:
        if tok.kind == "punct" and tok.value in "{([":
            depth += 1
        elif tok.kind == "punct" and tok.value in "})]":
            depth -= 1
        if depth == 0 and tok.kind == "punct" and tok.value in ",;":
            entries.append([])
            continue
        entries[-1].append(tok)
    return [e for e in entries if e]


def _entry_key(entry: list[Token]) -> tuple[str | None, list[Token]]:
    if len(entry) >= 3 and entry[0].kind == "name" and entry[1].value == "=":
        return entry[0].value, entry[2:]
    if len(entry) >= 5 and entry[0].value == "[" and entry[2].value == "]" and entry[3].value == "=":
        return entry[1].value, entry[4:]
    return None, entry


def _preview(entry: list[Token]) -> str:
    text = " ".join(t.value if t.kind != "string" else repr(t.value) for t in entry)
    return text[:_PREVIEW_CHARS] + ("…" if len(text) > _PREVIEW_CHARS else "")


def shape_of(inner: list[Token]) -> TableShape:
    """Shape of a table given the tokens between its braces."""
    shape = TableShape()
    for entry in _split_entries(inner):
        key, value = _entry_key(entry)
        shape.entries += 1
        shape.keyed += key is not None
        shape.positional += key is None
        shape.value_kinds[_value_kind(value[0])] += 1
        if value[0].value == "{" and value[0].kind == "punct":
            for sub in _split_entries(value[1:-1]):
                sub_key, _ = _entry_key(sub)
                if sub_key is not None:
                    shape.nested_keys[sub_key] += 1
        if len(shape.samples) < _SAMPLES:
            shape.samples.append(_preview(entry))
    return shape


def table_shape(source: str, line_start: int, line_end: int) -> TableShape | None:
    """Shape of the first table constructor starting within ``[line_start, line_end]``."""
    tokens = [t for t in tokenize(source) if line_start <= t.line <= line_end]
    try:
        start = next(i for i, t in enumerate(tokens) if t.kind == "punct" and t.value == "{")
    except StopIteration:
        return None
    depth = 0
    for i in range(start, len(tokens)):
        tok = tokens[i]
        if tok.kind == "punct" and tok.value == "{":
            depth += 1
        elif tok.kind == "punct" and tok.value == "}":
            depth -= 1
            if depth == 0:
                return shape_of(tokens[start + 1 : i])
    return shape_of(tokens[start + 1 :])


def call_histogram(source: str, top: int = 15) -> list[tuple[str, int, str]]:
    """Most repeated call targets (``obj:Method``/``fn``) with one sample line each."""
    tokens = list(tokenize(source))
    counts: Counter[str] = Counter()
    sample: dict[str, str] = {}
    lines = source.splitlines()
    for i in range(len(tokens) - 1):
        nxt = tokens[i + 1]
        if tokens[i].kind != "name" or nxt.kind != "punct" or nxt.value != "(":
            continue
        target = tokens[i].value
        if i >= 2 and tokens[i - 1].value in (":", ".") and tokens[i - 2].kind == "name":
            target = f"{tokens[i - 2].value}{tokens[i - 1].value}{target}"
        counts[target] += 1
        sample.setdefault(target, lines[tokens[i].line - 1].strip()[:120])
    return [(name, n, sample[name]) for name, n in counts.most_common(top)]
