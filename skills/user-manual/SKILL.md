---
name: user-manual
description: Generate and incrementally maintain a per-project user manual at `<project>/docs/manual/user-manual.md` plus a self-contained `user-manual.html` viewer, by analyzing the project's superpowers artifacts (`docs/superpowers/{specs,plans,findings,reviews}/`) and fortifying with web search. Trigger on `/user-manual`, "generate user manual", "create user manual", "update the user manual", "refresh the manual", "build a manual from the specs and plans", or any phrase asking for end-user / operator documentation drawn from project specs and plans. Idempotent across runs via a Citations section that records the SHA256 of every cited artifact — only new or changed artifacts are folded in on subsequent runs. Targets BOTH novices (Quick Start, jargon expansion, abbreviation glossary) AND experts (architecture, configuration, troubleshooting). Use this even when the user just says "document this for end users" or "make a user guide" since those are user-manual signals. Do not invoke for purely internal / developer-facing READMEs that aren't drawn from superpowers artifacts.
---

# User Manual

Generate and maintain a project user manual at `<project>/docs/manual/user-manual.md` (plus a self-contained `user-manual.html` viewer next to it) by reading the project's [superpowers](https://github.com/obra/superpowers) artifacts — specs, plans, findings, reviews — and synthesizing them into prose aimed at the people who will actually *use* the software, not the ones building it.

The skill is invoked when the user wants either:

- The first version of a manual (no `user-manual.md` exists yet), **or**
- An incremental update to an existing manual after new specs / plans / findings / reviews have landed.

Both cases use the same routine; the existing-manual case skips artifacts whose hashes haven't changed since the last run, so it stays cheap to re-run frequently.

## Why this skill exists

A project's superpowers folder is dense, design-document-y, and written for the team building the system. End users — the people who install, configure, run, and troubleshoot it — need something different: a Quick Start, a glossary, a daily-usage walkthrough, a configuration reference, a troubleshooting list. Asking a non-developer to read a 30-page spec to answer "how do I install this?" doesn't work.

The synthesis is hard for a human (lots of files, lots of jargon, easy to miss the "why"). It's tractable for an LLM: read the artifacts, write prose, expand abbreviations on first use, elaborate on dense technical passages, and link back to the source docs for readers who want the full design context.

The output is *one document* — a single `user-manual.md` with a hand-friendly structure — plus an HTML viewer for people who'd rather read in a browser.

## File location

- `<git-root>/docs/manual/user-manual.md` — the markdown the skill writes
- `<git-root>/docs/manual/user-manual.html` — the dashboard / viewer (created/regenerated only on template-version bumps)

If `docs/manual/` doesn't exist, create it. The `git-root` is the project root, even when invoked from a subdirectory: prefer `git rev-parse --show-toplevel` and fall back to `pwd` if it fails. Use `git rev-parse` for project-root detection; do not invent your own.

## Inputs the skill reads

The skill walks `<git-root>/docs/superpowers/` and looks for `*.md` files in four subdirectories:

| Folder | Kind | What it usually contains |
|---|---|---|
| `specs/` | spec | Design specs / architecture documents |
| `plans/` | plan | Implementation plans / staged rollouts |
| `findings/` | finding | Investigation results, root-cause writeups |
| `reviews/` | review | Code-review notes, retrospectives |

Other files in the superpowers folder are ignored — only those four subdirectories. If a project doesn't have a superpowers folder, fall back gracefully: tell the user the skill needs at least one populated `docs/superpowers/{specs,plans,findings,reviews}/` subdirectory and ask whether they want to seed the manual from a different source instead (e.g., a README + git log).

## File shape (canonical structure)

The manual has seven top-level sections in this exact order. The skill creates the scaffold via the helper script if the file is missing; on rerun, it preserves any user edits and only updates content drawn from artifacts.

```markdown
# User Manual

_Maintained by the [`user-manual`](https://github.com/photoenthu/user-manual-skill) skill._

## Quick Start

## Concepts and Glossary

## Daily Usage

## Configuration

## Troubleshooting and FAQ

## Architecture and Internals

## Citations

### Project artifacts
| Path | Kind | Title | SHA256 (content) | First cited (ET) | Last seen (ET) |
|---|---|---|---|---|---|

### External references
| URL | Title | Cited from section | Last fetched (ET) |
|---|---|---|---|
```

### What goes in each section

| Section | Audience-first answer |
|---|---|
| **Quick Start** | "How do I get this running for the first time, in 10 minutes?" Cover prerequisites, install, minimum viable config, smoke-test command, expected first-run output. Lead with the most common path; mention alternates only if a meaningful share of users will need them. Aim for a complete novice — they should be able to follow without referencing other docs. |
| **Concepts and Glossary** | Every term, abbreviation, and project-specific noun a reader will hit, defined in plain English. **Always expand abbreviations on first use** (e.g., "VWAP — Volume-Weighted Average Price"). Order alphabetically inside the section so it doubles as a lookup. |
| **Daily Usage** | What a competent user does on an ordinary day. Common workflows, command examples, tips, gotchas, output-interpretation guidance. This is the section experts re-read to refresh their memory. |
| **Configuration** | Every tunable parameter, env var, config file, and override the user might touch. Describe defaults, valid ranges, and why someone would change a value. Group by purpose (e.g., "Risk management knobs", "Logging knobs"), not alphabetically — purpose-grouping matches how users actually search. |
| **Troubleshooting and FAQ** | Symptoms → causes → fixes. Pull from `findings/` and `reviews/` aggressively here — root-cause writeups are gold for this section. Phrase as "If you see X…" rather than "X is caused by…" — readers search by symptom. |
| **Architecture and Internals** | For power users and contributors. Cross-link liberally to the source specs/plans. Pull diagrams (ASCII art, mermaid blocks, embedded images) directly into this section so the reader doesn't bounce out — the source artifact link still appears beneath each diagram for the full context. |
| **Citations** | Idempotency ledger. Two sub-tables: project artifacts (the superpowers files folded in, with content hashes for change detection) and external references (web pages cited for fortification). Skill-managed; do not hand-edit unless removing a stale entry. |

## When the skill is invoked

Run this checklist in order. The order matters because each step's output feeds the next.

### 1. Resolve paths and load existing state

```bash
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
MANUAL_MD="$ROOT/docs/manual/user-manual.md"
MANUAL_HTML="$ROOT/docs/manual/user-manual.html"
SKILL_DIR="$(dirname "$0")"  # or the absolute path the harness gives you
python3 "$SKILL_DIR/scripts/manual_helper.py" init "$MANUAL_MD"
```

The `init` subcommand writes the empty scaffold only if the file is missing — idempotent. Then read the file with the Read tool.

### 2. Diff the on-disk artifacts against the manual's existing citations

```bash
python3 "$SKILL_DIR/scripts/manual_helper.py" diff-artifacts "$ROOT" "$MANUAL_MD"
```

This emits JSON with four buckets:

- **`new`** — artifacts not in the citation table at all. These need a full read + integration pass.
- **`changed`** — artifacts in the citation table whose SHA256 has changed since last run. Re-read them; revise the affected sections of the manual; bump their `Last seen` timestamp and update their hash in Citations.
- **`unchanged`** — artifacts whose hash still matches. **Skip them.** Their hash and `Last seen` should not be touched. The manual's existing prose drawn from these artifacts is still authoritative.
- **`missing`** — artifacts cited in the table but no longer present on disk. Leave their citation row in place (mark a "(deleted)" suffix in the title cell so the historical reference is preserved), and flag them in the report at step 8 — the user may have intentionally removed them, or it may be a typo / move that should be addressed.

If all three buckets `new` / `changed` / `missing` are empty, tell the user the manual is up to date and exit early without touching the file. (Still run step 7 — HTML regeneration — in case the bundled template version was bumped.)

### 3. Read the artifacts that need processing

For each entry in `new` ∪ `changed`, read the file with the Read tool. Pay attention to:

- The H1 (the artifact's title — already extracted as `title` by the helper).
- Any abbreviations or jargon defined inline. Capture them for the Glossary.
- ASCII diagrams, mermaid blocks, dot blocks — these go into Architecture, ideally near the related prose.
- "Why" passages: motivation, constraints, failure modes. These usually belong in Troubleshooting or in a margin elaboration in Daily Usage.
- Status markers (`SHIPPED`, `DEFERRED`, `WIP`) — only fold in **shipped** behavior into a user manual. A spec that's still WIP describes future state, not current capability; flag it as future-state at the user's option, but default to leaving it out.

If `changed` artifacts substantially altered prior conclusions, the corresponding manual passages need revision, not just appending. Re-read the manual sections that cite that artifact and rewrite them in place.

### 4. Fortify with web search where it sharpens novice comprehension

The artifacts are written for the team that built the system; the manual is for end users. Two scenarios warrant a web fetch:

1. **Jargon you can't fully unpack from the artifacts alone.** If a term shows up unexplained ("the bot uses VWAP-reclaim entries"), and you can write a clearer one-paragraph explainer by pulling from the canonical web definition, do a `WebSearch` (or `WebFetch` if you have a specific URL in mind), cite it as an External Reference, and write the explainer in plain English. Don't link to the source as a substitute for the explanation — write the explanation, then cite.
2. **Abbreviation expansions you're not 100% sure of.** If "ADV" could be "Average Daily Volume" or "Advance" depending on context, look it up rather than guessing. Wrong abbreviation expansions are worse than missing ones.

For each external reference cited, append a row to the External References sub-table with the URL, the page title, the section of the manual that cites it, and the fetch timestamp from `python3 manual_helper.py now-et`. External references are **not** used for idempotency — the skill may re-fetch them on future runs to keep elaborations current.

**When NOT to web-search:** project-internal context (file paths, function names, config keys, anything visible in the artifacts) — the artifacts are authoritative. Don't web-search for "what does this codebase's `risk_calculator.py` do" — read the spec.

### 5. Write the manual

Use the Edit tool to make targeted changes — never overwrite the whole file. The skill works in **section-scoped passes**, not by rewriting top-to-bottom:

For each section in the canonical structure, decide whether the new + changed artifacts have material new content for that section. If yes, read the existing section, identify the right insertion point (or the passage to revise), and edit. If no, leave the section alone.

Style guidance:

- **Lead with intent, not mechanics.** A novice reading "Daily Usage" wants "what should I be doing?" before "how do I do it?". Write one-sentence framing before each command-list.
- **Expand abbreviations on first use, every section.** Don't assume a reader entered through the Glossary — many will land mid-document via search. "VWAP (Volume-Weighted Average Price)" the first time it appears in each top-level section is fine; once-per-document is too sparse.
- **Cross-reference superpowers files with embedded markdown links** wherever a curious reader would benefit from the source: `See the [original spec](../superpowers/specs/2026-04-02-foo-design.md) for the rejected alternatives.` Use **standard markdown convention — paths relative to the .md file the link appears in**. From `docs/manual/user-manual.md`, that means `../superpowers/...`, `../runbook.md`, `../../config/settings.yaml`, `../../CLAUDE.md`, etc. This works in raw GitHub views, in any markdown renderer, AND in the bundled HTML viewer (which resolves links against the .md file's directory and walks the project-root directory handle to fetch the bytes for in-page popups). Use the artifact's title (or a meaningful phrase) as link text — never raw paths.
- **Embed diagrams directly.** When an artifact contains an ASCII diagram, mermaid block, dot graph, or referenced image that explains structure / architecture / flow, copy it into the manual section that needs it. Place a "_Source: [link to artifact](relative/path.md)_" caption immediately below. The reader sees the diagram without bouncing.
- **Avoid jargon when a plain word works.** "Use the bot's emergency-stop command" beats "invoke the panic-flatten interlock." When jargon is unavoidable (industry-standard terms with no plain equivalent), use it consistently and define it.
- **Headings are stable URL anchors.** The HTML viewer slugifies every heading and uses it as both an anchor target and a TOC entry. Don't gratuitously rename headings on re-runs — bookmarks and external links rot.
- **Match section depth to reader need.** Quick Start should rarely need H4. Architecture often needs H4 / H5. Don't pad with empty subsections.

### 6. Update the Citations section

After the prose edits, append/update the project-artifact citation table. For each artifact processed:

- **New** → add a row. `First cited` and `Last seen` both = `python3 manual_helper.py now-et`. Hash = the value from `diff-artifacts`. Title = the artifact's H1. Path is wrapped as a markdown link: `[2026-04-02-foo-design.md](../superpowers/specs/2026-04-02-foo-design.md)` so the table is clickable in any markdown renderer. (The Citations table sits inside `user-manual.md` at `docs/manual/`, so the link path is relative to that file — same convention as everywhere else in the manual.)
- **Changed** → update the existing row in place. `First cited` is preserved (it's a historical record); `Last seen` = current ET timestamp; hash = the new hash from `diff-artifacts`.
- **Missing** → add ` (deleted)` to the title cell. Leave hash and timestamps untouched. The path link will 404 — that's the correct behavior; it makes the bit-rot visible.

The hash cell should be wrapped in inline-code backticks: `` `ed85ab04011abc08` ``. The helper's parser strips the backticks on read, so the round-trip stays clean.

### 7. Regenerate the HTML viewer if the bundled template is newer

```bash
python3 "$SKILL_DIR/scripts/manual_helper.py" regenerate-html-if-stale "$MANUAL_HTML"
```

Three possible outcomes:

- `created` — the HTML didn't exist; first-time write.
- `regenerated` — the file existed but its embedded version was older than the bundled template's.
- `unchanged` — already at current version; no write.

The HTML reads the markdown live via the browser's File System Access API (Chrome/Edge/Brave/Arc/etc.) or a one-shot file picker (Firefox/Safari). It does **not** need to be regenerated on every manual edit — only when the bundled template structure changes. Mention `created` / `regenerated` outcomes in the final report so the user knows their viewer file moved.

### 8. Report what changed

End with a one-line-per-bucket summary:

```
Manual updated: docs/manual/user-manual.md
  • 4 new artifacts cited (2 specs, 1 plan, 1 finding)
  • 1 changed artifact re-folded in
  • 0 unchanged (skipped)
  • 1 missing artifact flagged (docs/superpowers/plans/2026-03-15-cancelled.md)
  • 2 external references cited
HTML viewer: unchanged
```

If `missing` artifacts surfaced, ask the user whether they were intentional removals or whether the manual should be edited to remove the dependency.

### 9. Ask whether to commit and push

Surface this prompt **once** at the end:

> Commit and push `docs/manual/user-manual.md` (and `user-manual.html` if it was created/regenerated) to git? **(yes / skip)**

- **yes** — Stage **only** the manual files by explicit path:
  ```bash
  git add docs/manual/user-manual.md
  # plus the HTML if step 7 returned created or regenerated
  git add docs/manual/user-manual.html
  git commit -m "<message>"
  git push
  ```
  The commit message should be **one line**, concise, and describe what was added — e.g. `docs(manual): fold in 4 new specs + 1 finding`. Do not include the AI-attribution footer for these commits — they're routine docs maintenance.
- **skip** — leave the files modified in the working tree. The user will commit them later (or not).

If the working tree has unrelated dirty files, that's fine — staging by explicit path keeps them out. If the cwd isn't a git repo, skip the prompt with a one-line note: `Not a git repo; commit/push skipped.`

## HTML viewer

The skill bundles a self-contained dashboard at `templates/user-manual.html`. On every invocation, the skill copies it into the project's `docs/manual/user-manual.html` only when the bundled template's version exceeds the on-disk version. The version is a single integer in an HTML comment near the top:

```html
<!-- user-manual-dashboard-version: 1 -->
```

When the skill author edits the bundled template in a way that should trigger users to re-fetch (parser fix, new feature, fixed bug), they bump this integer. Otherwise it stays put — most skill updates won't touch the dashboard.

### What the viewer does

The HTML is **never bundled with manual content**. On first load, the user clicks **Open file…** and picks `user-manual.md`. The browser stores a persistent file handle (Chromium-based browsers) or falls back to a one-shot picker (Firefox/Safari). On subsequent visits, the dashboard re-renders without re-prompting.

The viewer:

- Renders the entire markdown as styled HTML — headings, paragraphs, lists, tables (GFM), fenced code blocks with language hints, blockquotes, inline code/bold/italic, links, images, horizontal rules.
- Generates a sticky **left-sidebar Table of Contents** from H2 / H3 / H4 headings, with a filter input and an active-section indicator that tracks scroll position.
- Opens **all hyperlinks in new windows** (`target="_blank" rel="noopener"`). External URLs go straight to the browser; relative paths to project artifacts (e.g. `docs/superpowers/specs/foo.md`) are fetched via the project-root directory handle and rendered inline as a popup viewer — no navigation away from the manual.
- Honors `prefers-color-scheme: light | dark`.
- Is fully self-contained — no CDN, no external CSS, no external JS. Works offline.

### Browser compatibility

| Browser | Persistent handle | Behavior |
|---|---|---|
| Chrome, Edge, Brave, Arc, Opera, other Chromium | yes | Pick once, reload, viewer renders. |
| Safari | no | Falls back to `<input type="file">`. User picks each visit. |
| Firefox | no | Same fallback as Safari. |

The fallback path is automatic.

## Examples

### Example 1 — First invocation in a fresh project

**Project state**: 12 specs, 8 plans, 2 findings, 1 review in `docs/superpowers/`. No `user-manual.md` exists.

**Skill behavior**:

1. Runs `init` → creates the scaffold at `docs/manual/user-manual.md`.
2. Runs `diff-artifacts` → all 23 files come back as `new`.
3. Reads each, groups them by section relevance, drafts prose for Quick Start / Concepts / Daily Usage / Configuration / Troubleshooting / Architecture.
4. Web-searches 4 unfamiliar abbreviations (VWAP, ADV, RTH, ZVOL); cites the canonical pages.
5. Writes 23 rows to project-artifact Citations + 4 rows to external Citations.
6. Calls `regenerate-html-if-stale` → returns `created`.
7. Reports: `Manual created at docs/manual/user-manual.md (~280 lines). 23 artifacts cited, 4 external refs. HTML viewer: created.`
8. Asks whether to commit + push. User confirms; both files go to git.

### Example 2 — Incremental update after one new spec

**Project state**: existing manual, citations table covers 23 artifacts. User just landed `docs/superpowers/specs/2026-05-04-new-feature.md` and re-invokes the skill.

**Skill behavior**:

1. `diff-artifacts` returns `new=1, changed=0, unchanged=23, missing=0`.
2. Reads the new spec, identifies which sections it affects (Daily Usage + Configuration + Architecture), edits those sections in place.
3. Appends one row to the citation table.
4. Calls `regenerate-html-if-stale` → `unchanged`.
5. Reports: `1 new artifact cited (spec). 0 changed. HTML viewer: unchanged.`
6. Asks to commit. User says yes; one tight commit lands.

### Example 3 — Mixed update with a deleted artifact

**Project state**: 1 cited artifact was deleted in a refactor; 2 plans were edited; 1 new finding was added.

**Skill behavior**:

1. `diff-artifacts` returns `new=1 (finding), changed=2 (plans), unchanged=20, missing=1 (deleted plan)`.
2. Reads the new finding → adds a Troubleshooting entry.
3. Reads the 2 changed plans → revises the corresponding Architecture and Daily Usage passages in place.
4. Marks the deleted artifact's citation row title with ` (deleted)` suffix; preserves the row.
5. Reports the missing artifact and asks: "The manual cites `docs/superpowers/plans/2026-03-15-cancelled.md` but the file is gone. Was that intentional? If so, I can also remove the prose passages that depend on it."

## Anti-patterns to avoid

- **Don't rewrite the whole file on every run.** The Citations table is the idempotency ledger; trust it. Only touch sections that the diff says have changed inputs.
- **Don't truncate the artifact's prose into the manual verbatim.** The manual is a different document for a different audience. Synthesize, don't copy.
- **Don't link to a superpowers file as a substitute for explanation.** A novice clicking through to a 600-line spec is a failure mode. Write the explanation in the manual; cite the spec for readers who want more.
- **Don't fold in WIP / cancelled artifacts.** The manual describes current shipped behavior. A spec marked "DEFERRED" or "REJECTED" doesn't belong in user-facing prose. (Citations may still record them if they were meaningful at the time.)
- **Don't web-search for project-internal facts.** The artifacts are authoritative for anything inside the codebase. Web search is for jargon, abbreviations, and external standards.
- **Don't skip the Glossary because "the abbreviations are obvious."** They're obvious to the team that built the system; the audience is everyone else. Always expand on first use, always anchor a Glossary entry.
- **Don't auto-archive `Last seen` timestamps for unchanged artifacts.** If the hash matches, neither the hash nor the timestamps move. The skill's idempotency depends on these being stable.
- **Don't auto-commit without asking.** The commit/push prompt is mandatory. Cheap to confirm, expensive to push the wrong thing.
- **Don't `git add .` or `git add -A`.** Stage the two manual files by explicit path. Other dirty files in the working tree are not the skill's concern.
- **Don't bump the HTML template's version comment unnecessarily.** The version gates regeneration in every project that uses the skill — bumping it for a typo fix triggers churn everywhere. Bump only when the change is meaningful for users.

## Why this skill, and not a static-site generator

A user manual maintained by a generator (MkDocs, Docusaurus, etc.) needs an explicit author for every page; a manual maintained by this skill needs only that the team keeps writing specs and plans. The team is already doing that. The skill's job is to translate those artifacts — written for builders — into a single document for readers, and to keep the translation in sync as the artifacts evolve.

The cost is structure: the manual lives at one fixed path, has seven fixed sections, and uses one fixed citation format. That structure is what makes the skill idempotent; without it, every rerun would have to re-derive its own conclusions. The discipline pays for itself the second time the skill runs.
