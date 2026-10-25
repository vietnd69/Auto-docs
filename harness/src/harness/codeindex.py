"""Deterministic codebase index: per-file domain, size, symbols and dependencies."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

from harness.domains import domain_of
from harness.lua_parse import FileFacts, LuaSymbol, parse_lua, public_symbols
from harness.textutil import estimate_tokens
from harness.workspace import Workspace

INDEX_VERSION = 1


@dataclass
class FileIndex:
    path: str
    domain: str
    tokens: int
    lines: int
    is_data: bool
    symbols: list[LuaSymbol]
    public: list[str]
    requires: list[str] = field(default_factory=list)
    events_listened: list[str] = field(default_factory=list)
    events_pushed: list[str] = field(default_factory=list)
    components: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    def symbol(self, qualname: str) -> LuaSymbol | None:
        return next((s for s in self.symbols if s.qualname == qualname), None)

    def to_json(self) -> dict[str, object]:
        data = asdict(self)
        data["symbols"] = [asdict(s) for s in self.symbols]
        return data

    @classmethod
    def from_json(cls, data: dict[str, object]) -> FileIndex:
        raw_symbols = data.pop("symbols")
        if not isinstance(raw_symbols, list):
            raise TypeError("index cache entry has no symbol list")
        return cls(symbols=[LuaSymbol(**s) for s in raw_symbols], **data)  # type: ignore[arg-type]


def build_file_index(path: str, source: str) -> FileIndex:
    stem = path.rsplit("/", 1)[-1].removesuffix(".lua")
    facts: FileFacts = parse_lua(source, module_name=stem[:1].upper() + stem[1:])
    return FileIndex(
        path=path,
        domain=domain_of(path, facts.is_data),
        tokens=estimate_tokens(source),
        lines=facts.total_lines,
        is_data=facts.is_data,
        symbols=facts.symbols,
        public=[s.qualname for s in public_symbols(facts)],
        requires=facts.requires,
        events_listened=facts.events_listened,
        events_pushed=facts.events_pushed,
        components=facts.components,
        tags=facts.tags,
    )


def index_file(ws: Workspace, path: str, rev: str | None = None) -> FileIndex:
    """Index one file at ``rev`` (served from the codebase cache when available)."""
    cached = _load_cache(ws, ws.git.rev_parse(rev or ws.rev))
    if cached is not None and path in cached:
        return cached[path]
    return build_file_index(path, ws.git.show(rev or ws.rev, path))


def index_codebase(ws: Workspace, rev: str | None = None) -> dict[str, FileIndex]:
    """Index every ``.lua`` file at ``rev``; cached on disk per commit SHA."""
    sha = ws.git.rev_parse(rev or ws.rev)
    cached = _load_cache(ws, sha)
    if cached is not None:
        return cached
    paths = ws.git.ls_files(sha)
    index: dict[str, FileIndex] = {}
    batch = 200
    for start in range(0, len(paths), batch):
        contents = ws.git.show_many(sha, paths[start : start + batch])
        for path, source in contents.items():
            index[path] = build_file_index(path, source)
    _save_cache(ws, sha, index)
    return index


_MEMO: dict[str, dict[str, FileIndex]] = {}


def _cache_file(ws: Workspace, sha: str) -> str:
    return str(ws.cache_path(f"index-v{INDEX_VERSION}-{sha[:12]}.json"))


def _load_cache(ws: Workspace, sha: str) -> dict[str, FileIndex] | None:
    if sha in _MEMO:
        return _MEMO[sha]
    try:
        with open(_cache_file(ws, sha), encoding="utf-8") as handle:
            raw = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    _MEMO[sha] = {path: FileIndex.from_json(item) for path, item in raw.items()}
    return _MEMO[sha]


def _save_cache(ws: Workspace, sha: str, index: dict[str, FileIndex]) -> None:
    _MEMO[sha] = index
    with open(_cache_file(ws, sha), "w", encoding="utf-8") as handle:
        json.dump({p: fi.to_json() for p, fi in index.items()}, handle)
