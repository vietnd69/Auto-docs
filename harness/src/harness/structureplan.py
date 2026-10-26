"""Build a source-pinned structural proposal; never launch model calls or publish docs."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from harness.codeindex import FileIndex, index_codebase
from harness.config import Settings, load_settings
from harness.lua_lexer import tokenize
from harness.plan import DocPlan, Page, SourceRef, owned_symbols, save_plan, symbol_tokens, validate_plan
from harness.workspace import make_workspace

SHA = "b729a8f68d4b635c21279e71723b9627f24c5c38"
BUILD = "759671"
REGISTRIES = {"AddRoom", "AddTask", "AddTaskSet", "AddLevel", "AddRecipe2"}
ROOT_GROUPS = {
    "modding": {"modutil", "mods", "modindex", "modcompatability"},
    "networking": {"netvars", "networking", "networkclientrpc", "shardnetworking", "entityreplica"},
    "actions": {"actions", "bufferedaction", "componentactions"},
    "crafting": {"recipe", "recipes", "recipes_filter", "cooking", "techtree", "containers"},
    "runtime": {
        "class",
        "metaclass",
        "entityscript",
        "entityscriptproxy",
        "scheduler",
        "main",
        "mainfunctions",
    },
    "utilities": {"util", "mathutil", "math2d", "vector3", "vecutil", "vec3util", "stringutil", "easing"},
}
DIRECTORIES = {
    "components": "components",
    "prefabs": "prefabs",
    "brains": "ai/brains",
    "behaviours": "ai/behaviours",
    "stategraphs": "ai/stategraphs",
    "widgets": "ui/widgets",
    "screens": "ui/screens",
    "map": "worldgen",
    "scenarios": "scenarios",
    "util": "utilities",
    "tools": "debugging",
    "cameras": "presentation/cameras",
    "nis": "presentation/cinematics",
}


def data_destination(path: str) -> tuple[str, str] | None:
    """Return logical page id and page type; only verified families are merged."""
    stem = path.removesuffix(".lua")
    if path.startswith("map/static_layouts/"):
        group = stem.rsplit("/", 1)[0].removeprefix("map/static_layouts")
        return "data/layouts" + group + "/catalog", "catalog"
    if stem.startswith(("speech_", "strings", "skin_strings", "languages/")):
        return f"data/strings/{stem}", "catalog"
    if stem in {"tuning", "tuning_override"}:
        return f"data/tuning/{stem}", "mixed-data"
    if stem.startswith("prepared") or stem in {"spicedfoods", "wintersfeastcookedfoods"}:
        return f"data/recipes/{stem}", "mixed-data"
    if stem in {
        "skins_defs_data",
        "skin_assets",
        "skin_affinity_info",
        "skin_set_info",
        "prefabs/skinprefabs",
    }:
        return f"data/skins/{stem.rsplit('/', 1)[-1]}", "catalog"
    return ("data/catalogs/scrapbook", "catalog") if stem == "screens/redux/scrapbookdata" else None


def destination(path: str) -> tuple[str, str]:
    data = data_destination(path)
    if data is not None:
        return data
    stem = path.removesuffix(".lua")
    if stem == "prefabs/axe":
        return "reference/prefabs/tools/axes", "prefab-family"
    if "/" in stem:
        directory, rest = stem.split("/", 1)
        return f"reference/{DIRECTORIES.get(directory, directory)}/{rest}", "api"
    for group, names in ROOT_GROUPS.items():
        if stem in names:
            return f"reference/{group}/{stem}", "api"
    if stem.startswith(("debug", "console", "profiler")):
        return f"reference/debugging/{stem}", "api"
    return f"reference/runtime/modules/{stem}", "api"


def topic(qualname: str) -> str:
    """Candidate responsibility groups, explicitly subject to semantic review."""
    name = qualname.lower()
    for group, pattern in (
        ("combat", "attack|damage|combat|hit|hurt|parry|block"),
        ("locomotion", "walk|run|locomot|jump|hop|swim|sink|dash|mount|ride"),
        ("targeting", "target|aggro|retarget|range"),
        ("interaction", "pickup|harvest|chop|mine|dig|build|craft|eat|drink|useitem|fish"),
        ("lifecycle", "death|dead|revive|respawn|save|load|remove|sleep|wake|freeze|frozen"),
    ):
        if re.search(pattern, name):
            return group
    return "configuration-and-support"


def source_signals(source: str) -> dict[str, object]:
    """Find literal registry/env/factory signals without treating matches as resolved exports."""
    tokens = list(tokenize(source))
    objects = []
    injected = []
    for i in range(len(tokens) - 4):
        a, b, c, d, e = tokens[i : i + 5]
        if a.kind == "name" and a.value in REGISTRIES and b.value == "(" and c.kind == "string":
            objects.append({"kind": "registry", "name": f"{a.value}:{c.value}", "line": a.line})
        if a.value == "env" and b.value == "." and d.value == "=" and e.value == "function":
            objects.append({"kind": "environment-api", "name": f"env.{c.value}", "line": a.line})
        if a.value == "CommonStates" and b.value == "." and d.value == "(":
            injected.append({"helper": c.value, "line": a.line})
        if a.kind == "name" and a.value in {"Prefab", "MakeAxe"} and b.value == "(" and c.kind == "string":
            objects.append({"kind": "prefab-candidate", "name": c.value, "line": a.line})
    return {"candidate_objects": objects, "injected_states": injected}


def work_units(page: Page, index: dict[str, FileIndex]) -> list[dict[str, object]]:
    units: list[dict[str, object]] = []
    group: list[dict[str, str]] = []
    cost = 0
    for file, qual in owned_symbols(page, index):
        sym = index[file].symbol(qual)
        if sym is None:
            raise ValueError(f"Unknown symbol {file}:{qual}")
        estimate = (sym.line_end - sym.line_start + 1) * index[file].tokens // max(1, index[file].lines)
        if group and (len(group) >= 8 or cost + estimate > 4000):
            units.append({"symbols": group, "estimated_source_tokens": cost})
            group, cost = [], 0
        group.append({"file": file, "symbol": qual})
        cost += estimate
    if group:
        units.append({"symbols": group, "estimated_source_tokens": cost})
    if not units:
        units.append(
            {"symbols": [], "task": "schema/catalog or registry extraction", "estimated_source_tokens": 0}
        )
    for unit in units:
        raw = json.dumps(unit, sort_keys=True).encode()
        unit["id"] = hashlib.sha256(raw).hexdigest()[:12]
        unit["source_token_budget"] = 4000
        unit["needs_range_split"] = int(unit["estimated_source_tokens"]) > 4000
    return units


def page_groups(index: dict[str, FileIndex]) -> tuple[dict[str, list[SourceRef]], dict[str, str]]:
    groups: dict[str, list[SourceRef]] = defaultdict(list)
    types = {}
    for path, fi in sorted(index.items()):
        dest, page_type = destination(path)
        if path.endswith("_replica.lua"):
            dest = dest.removesuffix("_replica") + "/replica"
        elif path.removesuffix(".lua") + "_replica.lua" in index:
            dest += "/server"
        parts: dict[str, list[str]] = defaultdict(list)
        for qual in fi.public:
            parts[topic(qual)].append(qual)
        if page_type == "api" and len(fi.public) > 30 and len(parts) > 1:
            groups[dest + "/index"] = [SourceRef(path)]
            types[dest + "/index"] = "overview"
            for name, quals in parts.items():
                groups[dest + "/" + name] = [SourceRef(path, quals)]
                types[dest + "/" + name] = "api"
        else:
            groups[dest].append(SourceRef(path, list(fi.public)))
            types[dest] = page_type
    return groups, types


NARRATIVES = {
    "getting-started/entity-component-model": ["entityscript.lua", "class.lua"],
    "getting-started/server-client-boundaries": ["entityreplica.lua", "netvars.lua"],
    "guides/adding-boat-drag": [
        "components/boatdrag.lua",
        "components/boatphysics.lua",
        "prefabs/anchor.lua",
    ],
    "systems/boats": ["components/boatdrag.lua", "components/boatphysics.lua", "prefabs/winch.lua"],
    "systems/combat": ["components/combat.lua", "components/combat_replica.lua", "actions.lua"],
    "systems/inventory": ["components/inventory.lua", "components/inventory_replica.lua", "containers.lua"],
}


def build_structure(index: dict[str, FileIndex], sources: dict[str, str]) -> DocPlan:
    groups, types = page_groups(index)
    for dest, files in NARRATIVES.items():
        refs = [SourceRef(f) for f in files if f in index]
        if refs:
            groups[dest], types[dest] = refs, dest.split("/")[0]
    pages = []
    details = {}
    for dest, refs in sorted(groups.items()):
        fi = index[refs[0].file]
        kind = "data" if types[dest] in {"catalog", "mixed-data"} else "api"
        if types[dest] in {"overview", "guides", "systems", "getting-started"}:
            kind = "overview"
        page = Page(
            dest,
            dest + ".md",
            dest.rsplit("/", 1)[-1].replace("-", " ").title(),
            fi.domain,
            kind,
            dest.split("/")[:-1],
            refs,
        )
        page.budget_tokens = max(12000, symbol_tokens(page, index))
        pages.append(page)
        signals = {r.file: source_signals(sources[r.file]) for r in refs}
        units = work_units(page, index)
        details[dest] = {
            "page_type": types[dest],
            "generation_mode": "hybrid" if kind == "data" else "ai-assisted",
            "runtime_scope": "needs-verification",
            "work_units": units,
            "review": ["source-contract", "whole-page-example-and-lifecycle"],
            "signals": {k: v for k, v in signals.items() if any(v.values())},
            "depends_on": sorted({dep for r in refs for dep in index[r.file].requires}),
            "dependency_status": "require-literals-only; consumer/claim dependencies need resolution",
            "candidate_topics": sorted({topic(q) for r in refs for q in r.symbols}) if len(units) > 3 else [],
            "structural_review_required": len(units) > 3 or any(any(v.values()) for v in signals.values()),
            "grouping_basis": "source-path and candidate symbol-name topics; not caller-verified",
        }
    plan = DocPlan({"build": BUILD, "sha": SHA}, pages)
    plan.structure = {
        "schema_version": 2,
        "status": "structural-proposal",
        "execution_ready": False,
        "execution_blockers": [
            "Resolve env APIs, prefab factories, registries and injected states into stable owned objects",
            "Implement work-unit executor and split oversized atomic symbols into bounded source ranges",
            "Verify responsibility groups, runtime scopes and claim-level consumer dependencies",
            "Pilot whole-page semantic review before promoting this plan for generation",
        ],
        "pages": details,
        "file_dispositions": {
            path: {
                "disposition": "reference"
                if destination(path)[1] not in {"catalog", "mixed-data"}
                else "catalog",
                "owner_pages": [
                    p.id for p in pages if p.kind != "overview" and any(r.file == path for r in p.sources)
                ],
            }
            for path in sorted(index)
        },
        "navigation": ["getting-started", "guides", "systems", "reference", "data", "changes"],
        "coverage_scope": "All Lua files and parser public symbols; candidate objects remain unresolved",
        "page_budget_semantics": "Page estimate only; execution budget belongs to work units",
    }
    return plan


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    base = load_settings()
    cfg = Settings(
        base.root,
        dict(
            base.values,
            scripts_dir=str(args.source.resolve()),
            state_dir=str(base.root / ".cache/structure-plan"),
        ),
    )
    ws = make_workspace(cfg, SHA)
    index = index_codebase(ws)
    sources = {}
    paths = sorted(index)
    for start in range(0, len(paths), 200):
        sources.update(ws.git.show_many(SHA, paths[start : start + 200]))
    plan = build_structure(index, sources)
    issues = validate_plan(plan, index)
    if issues:
        raise ValueError(str(issues[:20]))
    save_plan(plan, args.output)
    print(
        json.dumps(
            {
                "files": len(index),
                "pages": len(plan.pages),
                "kinds": dict(Counter(p.kind for p in plan.pages)),
                "validation_issues": len(issues),
                "execution_ready": False,
            }
        )
    )


if __name__ == "__main__":
    main()
