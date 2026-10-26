/**
 * Budget guard (Harness² c8 plugin): limits that the model cannot skip (goal G7).
 *
 * - at most HARNESS_MAX_STEPS tool calls per session, then the session is aborted;
 * - an identical tool call (same tool + same args) three times in a row is blocked;
 * - writing a section back to a previous version (A → B → A oscillation) is blocked.
 *
 * When the step budget is spent a marker file .harness/reports/budget/<job>.json is written
 * so the harness reports BUDGET_EXHAUSTED instead of a plain FAIL.
 */
import { createHash } from "node:crypto"
import { mkdirSync, writeFileSync } from "node:fs"
import { join } from "node:path"

type Decision = { ok: true } | { ok: false; reason: string; abort: boolean }

const REPEAT_LIMIT = 3

function digest(value: unknown): string {
  return createHash("sha256").update(JSON.stringify(value ?? null)).digest("hex").slice(0, 16)
}

class BudgetGuard {
  private steps = new Map<string, number>()
  private recent = new Map<string, string[]>()
  private sections = new Map<string, string[]>()
  private repairs = new Map<string, number>()
  private drafted = new Set<string>()
  private escalated = new Set<string>()

  readonly maxSteps: number
  readonly maxRepairs: number

  constructor(maxSteps: number, maxRepairs = 2) {
    this.maxRepairs = maxRepairs
    this.maxSteps = maxSteps
  }

  check(sessionID: string, tool: string, args: Record<string, unknown> | undefined): Decision {
    const steps = (this.steps.get(sessionID) ?? 0) + 1
    this.steps.set(sessionID, steps)
    if (steps > this.maxSteps) {
      return { ok: false, abort: true, reason: `BUDGET_EXHAUSTED: ${this.maxSteps} tool calls used` }
    }
    if (tool === "task" && args) {
      const role = String(args.subagent_type)
      if (["writer", "writer-experimental", "writer-escalation"].includes(role)) {
        const match = /^(write|repair|escalate):(.+)$/.exec(String(args.description))
        if (!match) return { ok: false, abort: false, reason: "Use task description write:<group>, repair:<group> or escalate:<group>." }
        const [, phase, group] = match
        if (role === "writer-escalation") {
          if (phase !== "escalate" || (this.repairs.get(group) ?? 0) < this.maxRepairs || this.escalated.has(group)) {
            return { ok: false, abort: false, reason: "Claude escalation requires two repair rounds and is allowed once per group." }
          }
          this.escalated.add(group)
        } else if (phase === "repair") {
          const used = this.repairs.get(group) ?? 0
          if (used >= this.maxRepairs) return { ok: false, abort: false, reason: "Two repair rounds used; call writer-escalation for unresolved sections." }
          this.repairs.set(group, used + 1)
        } else if (phase === "write") {
          if (this.drafted.has(group)) return { ok: false, abort: false, reason: "Group already drafted; use repair:<group>." }
          this.drafted.add(group)
        } else {
          return { ok: false, abort: false, reason: "Use writer-escalation for escalation." }
        }
      }
    }
    const signature = `${tool}:${digest(args)}`
    const history = [...(this.recent.get(sessionID) ?? []), signature].slice(-REPEAT_LIMIT)
    this.recent.set(sessionID, history)
    if (history.length === REPEAT_LIMIT && history.every((s) => s === signature)) {
      return { ok: false, abort: false, reason: `blocked: identical ${tool} call repeated ${REPEAT_LIMIT} times; change approach` }
    }
    if (tool.endsWith("doc_write_section") && args) {
      const key = `${sessionID}|${String(args.page_id)}|${String(args.heading)}`
      const versions = this.sections.get(key) ?? []
      const current = digest(args.markdown)
      if (versions.length >= 2 && versions.slice(0, -1).includes(current) && versions.at(-1) !== current) {
        return { ok: false, abort: false, reason: `blocked: ${String(args.heading)} reverted to an earlier version (oscillation); record the conflict in notes instead` }
      }
      this.sections.set(key, [...versions, current])
    }
    return { ok: true }
  }

  used(sessionID: string): number {
    return this.steps.get(sessionID) ?? 0
  }
}

function writeMarker(directory: string, job: string, reason: string): void {
  if (!job) return
  const dir = join(directory, ".harness", "reports", "budget")
  mkdirSync(dir, { recursive: true })
  writeFileSync(join(dir, `${job.replaceAll("/", "__")}.json`), JSON.stringify({ job, reason, at: new Date().toISOString() }))
}

type PluginInput = { client?: any; directory?: string }
type ToolInput = { tool: string; sessionID: string; callID?: string }
type ToolOutput = { args?: Record<string, unknown> }

// OpenCode invokes every exported function as a plugin, so only one default export exists;
// the guard and marker helpers ride along as properties for tests.
async function budgetPlugin({ client, directory }: PluginInput) {
  const guard = new BudgetGuard(Number(process.env.HARNESS_MAX_STEPS ?? 80), Number(process.env.HARNESS_REVIEW_ROUNDS ?? 2))
  const job = process.env.HARNESS_JOB ?? ""
  return {
    "tool.execute.before": async (input: ToolInput, output: ToolOutput) => {
      const decision = guard.check(input.sessionID, input.tool, output.args)
      if (decision.ok) return
      if (decision.abort) {
        writeMarker(directory ?? process.cwd(), job, decision.reason)
        await client?.session?.abort?.({ path: { id: input.sessionID } })
      }
      throw new Error(decision.reason)
    },
  }
}

export default Object.assign(budgetPlugin, { BudgetGuard, writeMarker })
