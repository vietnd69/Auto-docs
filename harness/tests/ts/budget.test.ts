import assert from "node:assert/strict"
import { mkdtempSync, existsSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { test } from "node:test"

import * as budget from "../../../.opencode/harness/plugin/budget.ts"

const BudgetPlugin = budget.default

const { BudgetGuard, writeMarker } = BudgetPlugin

test("allows calls under the step budget", () => {
  const guard = new BudgetGuard(3)
  assert.deepEqual(guard.check("s", "a", { x: 1 }), { ok: true })
  assert.deepEqual(guard.check("s", "b", { x: 2 }), { ok: true })
  assert.equal(guard.used("s"), 2)
})

test("aborts once the step budget is exceeded (boundary)", () => {
  const guard = new BudgetGuard(2)
  guard.check("s", "a", {})
  guard.check("s", "b", {})
  const third = guard.check("s", "c", {})
  assert.equal(third.ok, false)
  assert.equal(third.ok === false && third.abort, true)
})

test("budgets are per session", () => {
  const guard = new BudgetGuard(1)
  assert.equal(guard.check("s1", "a", {}).ok, true)
  assert.equal(guard.check("s2", "a", {}).ok, true)
})

test("blocks the third identical call in a row", () => {
  const guard = new BudgetGuard(50)
  guard.check("s", "dst-tools_lua_read", { file: "a.lua" })
  guard.check("s", "dst-tools_lua_read", { file: "a.lua" })
  const third = guard.check("s", "dst-tools_lua_read", { file: "a.lua" })
  assert.equal(third.ok, false)
  assert.equal(third.ok === false && third.abort, false)
})

test("blocks A→B→A section oscillation but allows A→B→C", () => {
  const guard = new BudgetGuard(50)
  const write = (md: string) =>
    guard.check("s", "dst-tools_doc_write_section", { page_id: "p", heading: "### `F()`", markdown: md })
  assert.equal(write("A").ok, true)
  assert.equal(write("B").ok, true)
  assert.equal(write("C").ok, true)
  assert.equal(write("A").ok, false)
})

test("plugin writes a budget marker and aborts the session", async () => {
  const dir = mkdtempSync(join(tmpdir(), "budget-"))
  process.env.HARNESS_MAX_STEPS = "1"
  process.env.HARNESS_JOB = "job-x"
  const aborted: string[] = []
  const client = { session: { abort: async ({ path }: { path: { id: string } }) => { aborted.push(path.id) } } }
  const hooks = await BudgetPlugin({ client, directory: dir })
  await hooks["tool.execute.before"]({ tool: "t", sessionID: "s1" }, { args: {} })
  await assert.rejects(hooks["tool.execute.before"]({ tool: "t", sessionID: "s1" }, { args: {} }), /BUDGET_EXHAUSTED/)
  assert.deepEqual(aborted, ["s1"])
  assert.ok(existsSync(join(dir, ".harness", "reports", "budget", "job-x.json")))
})

test("writeMarker ignores empty job ids", () => {
  const dir = mkdtempSync(join(tmpdir(), "budget-"))
  writeMarker(dir, "", "x")
  assert.equal(existsSync(join(dir, ".harness")), false)
})

test("two repair rounds then one Claude escalation per group across sessions", () => {
  const guard = new BudgetGuard(50)
  const call = (session: string, role: string, description: string, prompt: string) =>
    guard.check(session, "task", { subagent_type: role, description, prompt })
  assert.equal(call("a", "writer-escalation", "escalate:g1", "early").ok, false)
  assert.equal(call("a", "writer", "write:g1", "draft").ok, true)
  assert.equal(call("a", "writer", "repair:g1", "fix 1").ok, true)
  assert.equal(call("b", "writer", "repair:g1", "fix 2").ok, true)
  assert.equal(call("c", "writer", "repair:g1", "fix 3").ok, false)
  assert.equal(call("a", "writer-escalation", "escalate:g1", "fix remaining").ok, true)
  assert.equal(call("b", "writer-escalation", "escalate:g1", "again").ok, false)
  assert.equal(call("a", "writer", "write:g2", "another group").ok, true)
})
