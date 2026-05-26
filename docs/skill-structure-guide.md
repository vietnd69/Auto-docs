# Standard Structure of a Claude Skill

> Reference document for creating and understanding the structure of a skill in the Claude system.

---

## Overview

A skill is a directory containing instructions and resources that help Claude perform a specialized type of task.
Claude reads the skill before executing it, then follows the instructions inside.

```
my-skill/
├── SKILL.md                ← REQUIRED — main instructions
├── scripts/                ← optional — runnable Python/Bash code
│   ├── __init__.py
│   ├── process.py
│   └── utils.py
├── references/             ← optional — documents Claude reads when needed
│   ├── api-reference.md
│   └── domain-rules.md
└── assets/                 ← optional — templates, fonts, icons used for output
    ├── output_template.md
    └── base_layout.html
```

---

## SKILL.md — Required File

### Full Structure

```markdown
---
name: kebab-case-skill-name
description: >
  [1-2 sentences describing what the skill does.]

  USE THIS SKILL whenever a user asks to:
  - "[trigger phrase 1]", "[trigger phrase 2]"
  - "[specific context when to use]"
  Trigger even if phrasing is informal like "[informal question example]".
compatibility:              ← optional, rarely used
  tools: [bash, python]
  python: ">=3.10"
---

# Skill Name (Main Heading)

A short description of the skill's purpose and spirit.
Written for Claude to read, not for the end user.

---

## Workflow

### Step 1 — [Step Name]

Specific instructions. Written in the imperative form (commands).

### Step 2 — [Step Name]

...

---

## Output Format

Clearly describe the desired output format.
Use an explicit template if available:

    ALWAYS use this exact structure:
    # [Title]
    ## Section A
    ## Section B

---

## Examples

**Example 1:**
Input: ...
Output: ...

---

## Quality Checklist

- [ ] Check criterion 1
- [ ] Check criterion 2

---

## Error Handling

- Error situation A: how to handle it.
- Error situation B: how to handle it.
```

### Explanation of each section

#### YAML Frontmatter (the `---` section)

| Field | Required | Description |
|---|---|---|
| `name` | ✅ | Identifier in `kebab-case`, matching the folder name |
| `description` | ✅ | **Main trigger mechanism.** Must clearly state both "what it does" and "when to use". Write a bit "pushy" because Claude tends to undertrigger. |
| `compatibility` | ❌ | Only used when the skill requires special tools/dependencies |

> **Golden rule for `description`:** Don't just describe the function — you must specify the trigger context.
> Instead of *"Generate a report"*, write *"Generate a report. Use this skill whenever the user wants any kind of data report, even if they say 'summary', 'breakdown', or 'overview'."*

#### Body of SKILL.md

| Section | When needed | Notes |
|---|---|---|
| Opening description | Always | 1-2 sentences setting the direction/spirit |
| Workflow / Steps | Always | Imperative, with step numbers |
| Output Format | When output has a fixed structure | Use explicit templates |
| Examples | When format is complex | Specific Input → Output |
| Quality Checklist | Recommended | Claude self-checks before returning |
| Error Handling | When there are many edge cases | List situations + handling |
| Source Priority | When using multiple data sources | Priority table in case of conflicts |

**Limit:** SKILL.md should be under **500 lines**. If it exceeds this, split the content into `references/` and link to it from SKILL.md.

---

## `scripts/` — Runnable Code

### When to use

Use when the task is **deterministic and repetitive** — no LLM reasoning needed:
- File processing (parse, transform, convert)
- Calling APIs, calculating metrics
- Generating output from a template
- Any logic >30 lines that doesn't involve judgment calls

### Sample Structure

```
scripts/
├── __init__.py             ← required if called using `python -m scripts.name`
├── main.py                 ← main entry point
├── utils.py                ← shared helper functions
├── process_input.py        ← input processing
└── templates/              ← XML/HTML/text templates used by scripts
    └── base.xml
```

### How to call from SKILL.md

```markdown
## Step 2 — Generate output

Run the processor script:
```bash
python -m scripts.main --input "{input_path}" --output "{output_path}"
```

Arguments:
- `--input`: path to the uploaded file
- `--output`: save to `/mnt/user-data/outputs/result.docx`
```

### Real-world example (from `docx` skill)

```
docx/scripts/
├── __init__.py
├── accept_changes.py       ← handle tracked changes in Word
├── comment.py              ← add/delete/reply comments
└── office/                 ← XML helpers library for Office formats
```

---

## `references/` — Documents Claude reads when needed

### When to use

Use for **static, lengthy** knowledge that doesn't need to be loaded into context at all times:
- API documentation
- Domain rules, business logic
- Instructions by variant/domain (AWS vs GCP vs Azure)
- JSON schema definitions

### Sample Structure

```
references/
├── api-reference.md        ← full API endpoints + params
├── domain-rules.md         ← business logic rules
└── error-codes.md          ← error codes table and how to handle them
```

**Multi-domain pattern** — when the skill supports multiple variants:

```
references/
├── aws.md                  ← only read when deploying to AWS
├── gcp.md                  ← only read when deploying to GCP
└── azure.md                ← only read when deploying to Azure
```

### How to link from SKILL.md

```markdown
## Step 1 — Load relevant reference

Identify the deployment target, then read the appropriate file:
- AWS → `references/aws.md`
- GCP → `references/gcp.md`
- Azure → `references/azure.md`

Do NOT read all three — only the one that matches.
```

### Rules

- Files >300 lines → add a **Table of Contents** at the top of the file
- SKILL.md must state **when** and **under what conditions** to read which file
- Do not load all references into context if not necessary

---

## `assets/` — Static files used in output

### When to use

Use for files Claude will **copy, fill in, or inject data into**:
- Markdown/HTML templates with placeholders
- Base layouts where scripts will inject data
- Font files, SVG icons for generated documents

### Sample Structure

```
assets/
├── output_template.md      ← template Claude fills in for each section
├── report_base.html        ← HTML skeleton for generated reports
└── icon_set/
    ├── warning.svg
    └── success.svg
```

### Real-world example

```
dota2-hero-research/assets/
└── hero_template.md        ← template with fixed sections
                               Claude fetches data then fills it in
```

### How to use from SKILL.md

```markdown
## Step 2 — Fill the template

Read the template from: `assets/output_template.md`

Replace each `{placeholder}` with data from Step 1.
Do not add or remove sections from the template.
```

---

## 3-Layer Loading System (Progressive Disclosure)

This is the most important mechanism — controlling **how much context** Claude needs to read:

```
Layer 1 — METADATA (always in context)
┌─────────────────────────────────────────┐
│ name + description (~100 words)         │
│ → Claude uses this to decide to trigger │
└─────────────────────────────────────────┘
         ↓ (when the skill is triggered)
Layer 2 — SKILL.md BODY (loaded upon trigger)
┌─────────────────────────────────────────┐
│ Workflow, Output Format, Examples       │
│ Quality Checklist, Error Handling       │
│ Limit: <500 lines                       │
└─────────────────────────────────────────┘
         ↓ (when workflow requires)
Layer 3 — BUNDLED RESOURCES (loaded on demand)
┌─────────────────────────────────────────┐
│ scripts/ → run directly                 │
│ references/ → read when needed          │
│ assets/ → use when generating output    │
│ No size limit                           │
└─────────────────────────────────────────┘
```

**Design Principle:** Place it at the lowest possible layer. Only move it to a higher layer when absolutely necessary.

---

## Custom Directories

In addition to the 3 directories above, skills can use any name depending on the purpose:

| Directory Name | Purpose | Example |
|---|---|---|
| `agents/` | Prompts for specialized subagents | `agents/grader.md`, `agents/analyzer.md` |
| `themes/` | Preset data by variant | `themes/dark.md`, `themes/minimal.md` |
| `evals/` | Test cases to benchmark the skill | `evals/evals.json` |
| `eval-viewer/` | UI tool for human review | HTML + Python script |

---

## Full Example — Hypothetical Skill

The `report-generator` skill creates an analysis report from a CSV file:

```
report-generator/
├── SKILL.md
├── scripts/
│   ├── __init__.py
│   ├── parse_csv.py         ← reads CSV, validates, returns dict
│   ├── compute_stats.py     ← calculates mean, median, trend
│   └── render_html.py       ← injects data into base template
├── references/
│   ├── chart-types.md       ← when to use bar vs line vs pie
│   └── formatting-rules.md  ← rules for formatting numbers, dates
└── assets/
    ├── report_template.html ← HTML skeleton
    └── styles.css           ← stylesheet for the report
```

**SKILL.md** for this skill will:
1. Have a frontmatter defining triggers when the user mentions "report", "CSV analysis", "data report"
2. Workflow: parse → compute → choose chart type → render
3. Point to `references/chart-types.md` in the chart selection step
4. Point to `assets/report_template.html` in the render step
5. Run `python -m scripts.parse_csv` in the first step

---

## Checklist for creating a new skill

- [ ] `SKILL.md` has YAML frontmatter with `name` and `description`
- [ ] `description` includes both "what it does" and "when to trigger" — sufficiently pushy
- [ ] Workflow is written in imperative form, with clear step numbers
- [ ] SKILL.md is under 500 lines — if it exceeds, split into `references/`
- [ ] All reference files are pointed to from SKILL.md with clear conditions
- [ ] Reference files >300 lines have a Table of Contents
- [ ] Scripts have `__init__.py` if called with `-m`
- [ ] Asset templates do not have any placeholders left empty in the output
- [ ] Includes Quality Checklist or Error Handling if the workflow is complex