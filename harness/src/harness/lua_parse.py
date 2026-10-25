"""Lightweight structural parser for DST Lua scripts.

Recognises the patterns DST code actually uses (classes, methods, stategraph states,
event/action handlers, prefabs, top-level tables) and reports each symbol with its exact
line range so tools can serve one symbol at a time instead of whole files.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from harness.lua_lexer import Token, tokenize

_BLOCK_OPEN = frozenset({"function", "if", "do", "repeat"})
_BLOCK_CLOSE = frozenset({"end", "until"})
_PAIRS = {"{": "}", "(": ")", "[": "]"}


@dataclass(frozen=True)
class LuaSymbol:
    kind: str  # function | method | class | state | event_handler | action | table | prefab
    name: str
    qualname: str
    line_start: int
    line_end: int
    signature: str = ""
    local: bool = False


@dataclass
class FileFacts:
    symbols: list[LuaSymbol] = field(default_factory=list)
    requires: list[str] = field(default_factory=list)
    events_listened: list[str] = field(default_factory=list)
    events_pushed: list[str] = field(default_factory=list)
    components: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    exports: list[str] = field(default_factory=list)
    total_lines: int = 0
    data_lines: int = 0
    generated: bool = False

    @property
    def is_data(self) -> bool:
        """True for generated files or when ≥80% of the file is function-free table literals."""
        if self.generated:
            return True
        return self.total_lines > 0 and self.data_lines / self.total_lines >= 0.8


class _Parser:
    def __init__(self, tokens: list[Token], module_name: str = "") -> None:
        self.t = tokens
        self.module_name = module_name or "module"
        self.class_ranges: list[tuple[int, int, str]] = []
        self.match: dict[int, int] = {}
        self.block_depth: list[int] = []
        self.brace_depth: list[int] = []
        self.paren_depth: list[int] = []
        self.facts = FileFacts()
        self._index_structure()

    # -- structure -------------------------------------------------------------------
    def _index_structure(self) -> None:
        blocks: list[int] = []
        brackets: list[int] = []
        braces = parens = 0
        for i, tok in enumerate(self.t):
            self.block_depth.append(len(blocks))
            self.brace_depth.append(braces)
            self.paren_depth.append(parens)
            if tok.kind == "keyword" and tok.value in _BLOCK_OPEN:
                blocks.append(i)
            elif tok.kind == "keyword" and tok.value in _BLOCK_CLOSE and blocks:
                self.match[blocks.pop()] = i
            elif tok.kind == "punct" and tok.value in _PAIRS:
                brackets.append(i)
                braces += tok.value == "{"
                parens += tok.value == "("
            elif tok.kind == "punct" and tok.value in ("}", ")", "]") and brackets:
                opener = brackets.pop()
                self.match[opener] = i
                braces -= self.t[opener].value == "{"
                parens -= self.t[opener].value == "("

    def is_(self, i: int, value: str) -> bool:
        return 0 <= i < len(self.t) and self.t[i].value == value and self.t[i].kind != "string"

    def kind_at(self, i: int) -> str:
        return self.t[i].kind if 0 <= i < len(self.t) else ""

    def end_line(self, opener: int) -> int:
        closer = self.match.get(opener)
        return self.t[closer].line if closer is not None else self.t[-1].line

    def top_statement(self, i: int) -> bool:
        return self.block_depth[i] == 0 and self.brace_depth[i] == 0 and self.paren_depth[i] == 0

    def params(self, open_paren: int) -> str:
        closer = self.match.get(open_paren, open_paren)
        return "".join(
            tok.value + (" " if tok.value == "," else "") for tok in self.t[open_paren + 1 : closer]
        )

    # -- lvalue helpers ----------------------------------------------------------------
    def lvalue_before(self, eq_index: int) -> tuple[int, str] | None:
        """Walk back from ``=`` over ``A.B.C`` / ``local A``; return (start index, name)."""
        j = eq_index - 1
        parts: list[str] = []
        while j >= 0 and self.kind_at(j) == "name":
            parts.insert(0, self.t[j].value)
            if not self.is_(j - 1, "."):
                break
            j -= 2
        if not parts or (j > 0 and self.t[j - 1].value in (".", ":")):
            return None
        start = j - 1 if self.is_(j - 1, "local") else j
        return start, ".".join(parts)

    # -- symbol detectors --------------------------------------------------------------
    def enclosing_class(self, i: int) -> str | None:
        for start, end, name in self.class_ranges:
            if start < i < end:
                return name
        return None

    def named_function(self, i: int) -> None:
        if self.block_depth[i] != 0:
            self.closure_method(i)
            return
        j, parts, sep = i + 1, [], "."
        while self.kind_at(j) == "name":
            parts.append(self.t[j].value)
            if self.is_(j + 1, ".") or self.is_(j + 1, ":"):
                sep = self.t[j + 1].value if self.is_(j + 1, ":") else sep
                j += 2
                continue
            j += 1
            break
        if not parts or not self.is_(j, "("):
            return
        local = self.is_(i - 1, "local")
        qual = ".".join(parts[:-1]) + (sep + parts[-1] if len(parts) > 1 else parts[-1])
        kind = "method" if sep == ":" and len(parts) > 1 else "function"
        start = self.t[i - 1].line if local else self.t[i].line
        self.add(kind, parts[-1], qual, start, self.end_line(i), f"{qual}({self.params(j)})", local)

    def closure_method(self, i: int) -> None:
        """``function self:Foo()`` inside a ``Class(function(self, ...) ... end)`` closure."""
        owner = self.enclosing_class(i)
        if owner is None or not self.is_(i + 1, "self") or self.t[i + 2].value not in (":", "."):
            return
        if self.kind_at(i + 3) != "name" or not self.is_(i + 4, "("):
            return
        name = self.t[i + 3].value
        qual = f"{owner}:{name}"
        self.add("method", name, qual, self.t[i].line, self.end_line(i), f"{qual}({self.params(i + 4)})")

    def anonymous_class(self, i: int) -> None:
        """``return Class(function(self, inst) ... end)`` (world components)."""
        if not self.is_(i - 1, "return") or self.block_depth[i] != 0 or not self.is_(i + 1, "("):
            return
        name = self.module_name
        self.class_ranges.append((i + 1, self.match.get(i + 1, len(self.t)), name))
        self.add("class", name, name, self.t[i].line, self.end_line(i + 1), self.class_sig(i + 1, name))

    def assigned_value(self, i: int) -> None:
        """``X = function(...)``, ``X = Class(...)`` or ``X = { ... }`` at top level."""
        if not self.is_(i - 1, "=") or not self.top_statement(i - 1):
            return
        found = self.lvalue_before(i - 1)
        if found is None:
            return
        start, qual = found
        local = self.is_(start, "local")
        name = qual.rsplit(".", 1)[-1]
        line = self.t[start].line
        tok = self.t[i]
        if tok.value == "function" and self.is_(i + 1, "("):
            sig = f"{qual}({self.params(i + 1)})"
            self.add("function", name, qual, line, self.end_line(i), sig, local)
        elif tok.value == "Class" and self.is_(i + 1, "("):
            self.class_ranges.append((i + 1, self.match.get(i + 1, len(self.t)), qual))
            self.add("class", name, qual, line, self.end_line(i + 1), self.class_sig(i + 1, qual), local)
        elif tok.value == "{":
            self.add("table", name, qual, line, self.end_line(i), "", local)

    def class_sig(self, open_paren: int, qual: str) -> str:
        closer = self.match.get(open_paren, open_paren)
        for j in range(open_paren + 1, closer):
            if self.is_(j, "function") and self.is_(j + 1, "("):
                return f"{qual}({self.params(j + 1)})"
        return f"{qual}()"

    def call_with_string(self, i: int) -> tuple[str, int] | None:
        """``Name("x", ...)`` / ``Name{ ... }`` helpers: (first string arg, opener index)."""
        if self.is_(i + 1, "(") and self.kind_at(i + 2) == "string":
            return self.t[i + 2].value, i + 1
        return None

    def state(self, i: int) -> None:
        opener = i + 1 if self.is_(i + 1, "{") else i + 2 if self.is_(i + 2, "{") else -1
        if opener < 0 or self.block_depth[i] != 0:
            return
        closer = self.match.get(opener, opener)
        for j in range(opener + 1, closer - 2):
            if (
                self.brace_depth[j] == self.brace_depth[opener] + 1
                and self.is_(j, "name")
                and self.is_(j + 1, "=")
                and self.kind_at(j + 2) == "string"
            ):
                name = self.t[j + 2].value
                self.add("state", name, f"State:{name}", self.t[i].line, self.end_line(opener))
                return

    def handler(self, i: int, kind: str) -> None:
        if self.block_depth[i] != 0 or self.brace_depth[i] > 1 or not self.is_(i + 1, "("):
            return  # handlers nested inside a State belong to that state
        if kind == "event_handler" and self.kind_at(i + 2) == "string":
            name = self.t[i + 2].value
            self.facts.events_listened.append(name)
        elif kind == "action" and self.is_(i + 2, "ACTIONS") and self.is_(i + 3, "."):
            name = self.t[i + 4].value
        else:
            return
        prefix = "EventHandler" if kind == "event_handler" else "Action"
        self.add(kind, name, f"{prefix}:{name}", self.t[i].line, self.end_line(i + 1))

    def facts_call(self, i: int, value: str) -> None:
        found = self.call_with_string(i)
        if found is None:
            if value == "require" and self.kind_at(i + 1) == "string":
                self.facts.requires.append(self.t[i + 1].value)
            return
        arg, opener = found
        if value == "require":
            self.facts.requires.append(arg)
        elif value == "ListenForEvent":
            self.facts.events_listened.append(arg)
        elif value == "PushEvent":
            self.facts.events_pushed.append(arg)
        elif value == "AddComponent":
            self.facts.components.append(arg)
        elif value == "AddTag":
            self.facts.tags.append(arg)
        elif value == "Prefab":
            self.add("prefab", arg, f"Prefab:{arg}", self.t[i].line, self.end_line(opener))

    def exports(self, i: int) -> None:
        if self.block_depth[i] != 0 or not self.is_(i + 1, "{"):
            return
        closer = self.match.get(i + 1, i + 1)
        self.add("table", "return", "return", self.t[i].line, self.t[closer].line)
        depth = self.brace_depth[i + 1] + 1
        for j in range(i + 2, closer):
            if self.brace_depth[j] == depth and self.kind_at(j) == "name" and self.is_(j + 1, "="):
                self.facts.exports.append(self.t[j].value)

    # -- driver ----------------------------------------------------------------------
    def add(
        self, kind: str, name: str, qual: str, start: int, end: int, sig: str = "", local: bool = False
    ) -> None:
        self.facts.symbols.append(LuaSymbol(kind, name, qual, start, end, sig, local))

    def literal_table_lines(self) -> int:
        """Lines covered by outermost table constructors that contain no function."""
        fn_prefix = [0]
        for tok in self.t:
            fn_prefix.append(fn_prefix[-1] + (tok.kind == "keyword" and tok.value == "function"))
        covered_until = -1
        lines = 0
        for i, tok in enumerate(self.t):
            if i <= covered_until or tok.kind != "punct" or tok.value != "{":
                continue
            closer = self.match.get(i)
            if closer is None or fn_prefix[closer] - fn_prefix[i] > 0:
                continue
            covered_until = closer
            lines += self.t[closer].line - tok.line + 1
        return lines

    def run(self) -> FileFacts:
        for i, tok in enumerate(self.t):
            self.dispatch(i, tok)
        if self.t:
            self.facts.total_lines = self.t[-1].line
        self.facts.data_lines = self.literal_table_lines()
        for attr in ("requires", "events_listened", "events_pushed", "components", "tags", "exports"):
            setattr(self.facts, attr, list(dict.fromkeys(getattr(self.facts, attr))))
        return self.facts

    def dispatch(self, i: int, tok: Token) -> None:
        if tok.kind == "keyword" and tok.value == "function":
            if self.kind_at(i + 1) == "name":
                self.named_function(i)
            else:
                self.assigned_value(i)
        elif tok.kind == "keyword" and tok.value == "return":
            self.exports(i)
        elif tok.kind == "punct" and tok.value == "{":
            self.assigned_value(i)
        elif tok.kind == "name":
            self.dispatch_name(i, tok.value)

    def dispatch_name(self, i: int, value: str) -> None:
        if value == "Class":
            self.anonymous_class(i) if self.is_(i - 1, "return") else self.assigned_value(i)
        elif value == "State":
            self.state(i)
        elif value == "EventHandler":
            self.handler(i, "event_handler")
        elif value == "ActionHandler":
            self.handler(i, "action")
        elif value in ("require", "ListenForEvent", "PushEvent", "AddComponent", "AddTag", "Prefab"):
            self.facts_call(i, value)
        elif value == "components" and self.is_(i + 1, ".") and self.kind_at(i + 2) == "name":
            self.facts.components.append(self.t[i + 2].value)


def parse_lua(source: str, module_name: str = "") -> FileFacts:
    """Parse ``source`` into structural facts. Never raises on malformed input.

    ``module_name`` names anonymous ``return Class(...)`` modules (usually the file stem).
    """
    tokens = list(tokenize(source))
    facts = _Parser(tokens, module_name).run()
    facts.total_lines = max(facts.total_lines, source.count("\n") + 1)
    facts.generated = "AUTOGENERATED" in source[:400].upper()
    return facts


_PUBLIC_KINDS = frozenset({"method", "class", "state", "event_handler", "action", "prefab"})


def public_symbols(facts: FileFacts) -> list[LuaSymbol]:
    """Symbols a page documenting this file must cover.

    Public = methods, classes, states, handlers, prefabs, non-local functions/tables and
    anything exported through the module's ``return { ... }`` table. A file that exposes
    none of these (plain scripts) falls back to its top-level local functions.
    """
    exported = set(facts.exports)
    chosen = [s for s in facts.symbols if s.kind in _PUBLIC_KINDS or not s.local or s.name in exported]
    if not chosen:
        chosen = [s for s in facts.symbols if s.kind == "function"]
    seen: set[str] = set()
    unique: list[LuaSymbol] = []
    for sym in chosen:
        if sym.qualname not in seen:
            seen.add(sym.qualname)
            unique.append(sym)
    return unique
