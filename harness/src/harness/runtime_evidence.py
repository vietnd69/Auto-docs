"""Controller-executed language probes, never arbitrary model-authored code.

These observations describe this standalone LuaJIT binary, not the DST engine,
component behavior or all possible operand types/metamethods.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

PROBE = r'''
assert(jit and jit.version, "LuaJIT required")
print("runtime=" .. jit.version .. "; language=" .. _VERSION)
local function check(id, fn)
    assert(fn(), id)
    print(id .. "=PASS")
end
check("numeric_string_add", function() return "5" + 2 == 7 end)
check("numeric_string_negate", function() return -"5" == -5 end)
check("numeric_string_math_min", function() return math.min(3, "2") == 2 end)
check("numeric_string_format_g", function() return string.format("%g", "5") == "5" end)
check("numeric_string_comparison_errors", function() return not pcall(function() return "5" < 0 end) end)
check("nonnumeric_string_add_errors", function() return not pcall(function() return "oops" + 2 end) end)
check("nonnumeric_string_format_errors", function() return not pcall(string.format, "%g", "oops") end)
check("false_format_errors", function() return not pcall(string.format, "%g", false) end)
check("false_fallback_zero", function() local t = {x=false}; return (t.x or 0) == 0 end)
check("false_magnitude_defaults", function() local x=false; return (x or 1) == 1 end)
check("zero_is_truthy", function() return (0 or 1) == 0 end)
check("nil_key_read", function() local t={}; return t[nil] == nil end)
check("nil_key_write_errors", function() return not pcall(function() local t={}; t[nil]=nil end) end)
check("nan_key_write_errors", function() return not pcall(function() local t={}; t[0/0]=nil end) end)
check("zero_division_inf", function() return 1/0 == math.huge end)
check("zero_division_nan", function() local x=0/0; return x ~= x end)
print("PROBE_COMPLETE")
'''.strip() + "\n"

OBSERVATIONS = (
    'Numeric string "5": addition with 2 gives 7; unary minus gives -5; '
    'math.min(3,"2") gives 2; string.format("%g","5") gives "5". '
    'Comparison "5" < 0 errors. Nonconvertible string "oops" errors for addition and %g; '
    'false errors for %g. A stored false falls back through or 0; false or 1 yields 1; '
    'zero is truthy. Reading a nil key from a plain table returns nil; writing nil or NaN '
    'keys errors even when assigning nil. Division 1/0 produces +inf and 0/0 produces NaN.'
)


def collect(ws, job) -> str:
    """Run once for this job; fail before model dispatch if evidence cannot be verified."""
    binary = ws.settings.get_str("runtime_lua_bin") or shutil.which("luajit")
    if not binary:
        raise FileNotFoundError("Runtime evidence requires LuaJIT; configure runtime_lua_bin")
    executable = Path(binary).resolve(strict=True)
    binary_hash = hashlib.sha256(executable.read_bytes()).hexdigest()
    result = subprocess.run([str(executable), "-"], input=PROBE, capture_output=True,
                            text=True, encoding="utf-8", timeout=10, check=False,
                            env={k: v for k, v in os.environ.items() if not k.upper().startswith("LUA")})
    lines = result.stdout.strip().splitlines()
    expected = [line.split('"', 2)[1] + "=PASS" for line in PROBE.splitlines() if line.startswith('check("')]
    if (result.returncode or len(lines) != len(expected) + 2
            or not lines[0].startswith("runtime=LuaJIT ")
            or lines[1:-1] != expected or lines[-1] != "PROBE_COMPLETE"):
        raise ValueError("Runtime probes failed or output incomplete; no verified evidence")
    if hashlib.sha256(executable.read_bytes()).hexdigest() != binary_hash:
        raise ValueError("LuaJIT executable changed during probe")
    record = dict(job_id=job.id, page_id=job.page_id, source_sha=ws.git.rev_parse(ws.rev),
                  executable=str(executable), executable_sha256=binary_hash,
                  probe_sha256=hashlib.sha256(PROBE.encode()).hexdigest(), probe=PROBE,
                  stdout=result.stdout, observations=OBSERVATIONS,
                  scope="Standalone LuaJIT language probes only; no DST engine or component execution")
    path = ws.report_path(f"runtime-evidence/{job.id}.json")
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return ("\n\nController-verified runtime evidence (data, not instructions):\n"
            + lines[0] + "\n" + OBSERVATIONS + "\n"
            + "Probe SHA256: " + record["probe_sha256"] + "\n"
            + "Scope: " + record["scope"] + ". Do not claim in-game validation. "
            + "Use this evidence for matching language operations when reviewing the pinned source; "
            + "do not defer these tested cases as unverified runtime assumptions. "
            + "Other types, metamethods and untested cases remain unverified. "
            + "Findings still require exact source quotes and current draft contradictions.\n")
