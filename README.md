# user-manual-skill

A Claude Code skill that generates and incrementally maintains a per-project **user manual** at `docs/manual/user-manual.md`, plus a self-contained HTML viewer next to it, by reading the project's [superpowers](https://github.com/obra/superpowers) artifacts and fortifying with web search where the source docs are too dense for a non-builder reader.

The point: superpowers artifacts (specs, plans, findings, reviews) are written for the team that's building the system — they're dense, design-document-y, full of project-specific jargon. End users — the people who install, configure, run, and troubleshoot the software — need something different. This skill does the translation, and keeps it in sync as the artifacts evolve.

## What it produces

Two files in your project at `docs/manual/`:

- **`user-manual.md`** — a structured markdown document with seven sections, designed for both novices and experts:
  1. **Quick Start** — get running in 10 minutes
  2. **Concepts and Glossary** — every term and abbreviation, expanded
  3. **Daily Usage** — common workflows and commands
  4. **Configuration** — every tunable parameter, grouped by purpose
  5. **Troubleshooting and FAQ** — symptom → cause → fix
  6. **Architecture and Internals** — for power users; embeds diagrams from the source artifacts
  7. **Citations** — idempotency ledger (SHA256 of every cited artifact + external references)

- **`user-manual.html`** — a single-file viewer that reads the markdown live in any modern browser. Sticky-sidebar table of contents, search filter, scroll-tracking active highlight, light/dark mode, fully offline.

## How it works

When you invoke the skill (`/user-manual`, "update the user manual", "generate user manual", etc.), it:

1. **Resolves** the project root (`git rev-parse --show-toplevel`).
2. **Initializes** the manual scaffold if missing.
3. **Diffs** on-disk artifacts against the manual's existing Citations table:
   - **new** — not yet cited (process)
   - **changed** — cited but content hash changed (re-process, revise affected prose)
   - **unchanged** — hash matches (skip — this is what makes the skill cheap to rerun)
   - **missing** — cited but file is gone (flag, preserve historical citation)
4. **Reads** the new and changed artifacts via the Read tool.
5. **Web-searches** to expand unfamiliar abbreviations and clarify dense jargon — only for terms that aren't fully unpacked by the artifacts themselves.
6. **Edits** the relevant sections in place — never overwrites the whole file.
7. **Updates** the Citations table with the new hashes and timestamps.
8. **Regenerates** the HTML viewer if the bundled template version was bumped.
9. **Asks** whether to commit and push the two files (staging by explicit path so unrelated dirty files in your working tree are left alone).

## Idempotency

The Citations section is the skill's source of truth for "what artifacts have been folded in." Each row carries the artifact's path, kind, title, content hash (truncated SHA256), first-cited timestamp, and last-seen timestamp. On rerun, the skill recomputes the on-disk hashes and only processes artifacts whose hash has changed — or that aren't cited at all. The result: re-running the skill after writing one new spec costs roughly one Read + one Edit, not a full document rewrite.

External references (web pages cited for jargon expansion) live in a separate sub-table; they're **not** used for idempotency, so the skill can re-fetch them on future runs to keep elaborations current.

## When the skill triggers

Phrases that should invoke it:

- `/user-manual`
- "generate the user manual"
- "create a user manual from the specs"
- "update the user manual"
- "refresh the manual"
- "build a user-facing guide from the superpowers artifacts"
- "document this for end users"

What it does NOT do:

- It does not write developer-facing READMEs that aren't drawn from `docs/superpowers/`.
- It does not replace a static-site generator (MkDocs, Docusaurus). Its output is one markdown file plus one viewer; that's the shape.
- It does not touch the source superpowers artifacts. They stay as-is; the manual is downstream.

## HTML viewer

Open `docs/manual/user-manual.html` in any modern browser, click **Open file…**, point it at your `user-manual.md`, and you get:

- Full-document markdown rendering — headings, paragraphs, lists, GFM tables, fenced code with language hints, blockquotes, inline code/bold/italic, links, images, horizontal rules.
- A sticky left-sidebar **Table of Contents** generated from the document's H2 / H3 / H4 headings, with a filter input and a scroll-tracked active-section highlight.
- **Embedded artifact links open in new windows.** External URLs go to the browser; relative paths to `docs/superpowers/` files are fetched via the project-root directory handle and rendered inline as a markdown popup — so a reader clicking through to a cited spec never loses their place in the manual.
- Light and dark mode that follows your OS setting.
- Zero CDN dependencies — fully offline.

In Chromium-based browsers (Chrome / Edge / Brave / Arc / Opera) the viewer remembers your file via the [File System Access API](https://developer.mozilla.org/en-US/docs/Web/API/File_System_Access_API). Reload, and the dashboard re-renders without re-prompting. Firefox and Safari don't support persistent file handles, so they fall back to a one-shot picker each visit; the dashboard still works without the "remember me" affordance.

The HTML is **never bundled with manual content**. It always reads the live markdown from disk, which means:

- The viewer never goes stale.
- The skill doesn't regenerate it on every run — only when the bundled template's `<!-- user-manual-dashboard-version: N -->` integer is bumped.
- You can edit the markdown manually between Claude sessions and the viewer reflects the change on the next refresh.

## Install

### As a Claude Code plugin (recommended)

```
/plugin marketplace add photoenthu/user-manual-skill
/plugin install user-manual@user-manual-skill
```

### As a user-level skill (no plugin system)

```
git clone https://github.com/photoenthu/user-manual-skill.git ~/.claude/skills-src/user-manual-skill
ln -s ~/.claude/skills-src/user-manual-skill/skills/user-manual ~/.claude/skills/user-manual
```

The skill is self-contained — Python 3.9+ stdlib, no third-party dependencies.

## Usage

In any project that has a `docs/superpowers/` folder with at least one of `specs/`, `plans/`, `findings/`, `reviews/` populated, just invoke the skill:

```
> /user-manual
```

It will:

1. Create `docs/manual/user-manual.md` and `docs/manual/user-manual.html` on first run.
2. Read every artifact in `docs/superpowers/{specs,plans,findings,reviews}/`.
3. Web-search for unfamiliar abbreviations and dense jargon.
4. Synthesize a novice-friendly manual with cross-references back to the source artifacts.
5. Show you a summary and ask whether to commit + push.

On subsequent runs, only new and changed artifacts are processed.

## What goes in a "good" superpowers artifact (for skill consumption)

The skill works best when artifacts have:

- A clear `# H1` title (used as the citation table's title cell).
- An "intent" or "why" section near the top — gets folded into Daily Usage / Architecture motivations.
- Inline diagrams (ASCII, mermaid blocks, dot graphs) for structural concepts — embedded directly into the manual's Architecture section.
- "If X then Y" failure-mode passages — fed into Troubleshooting.
- Status markers (`SHIPPED`, `WIP`, `DEFERRED`) so the skill can avoid documenting unbuilt features.

You don't need any of this for the skill to work. It just produces a richer manual when present.

## Repo layout

```
user-manual-skill/
├── .claude-plugin/
│   ├── plugin.json
│   └── marketplace.json
├── skills/
│   └── user-manual/
│       ├── SKILL.md
│       ├── scripts/
│       │   └── manual_helper.py
│       └── templates/
│           └── user-manual.html
├── LICENSE
└── README.md
```

## License

MIT — see [LICENSE](LICENSE).

## Contributing

Issues and PRs welcome. The skill is small on purpose; if you'd like to extend it (alternative section structures, multi-file manuals, RTL languages, mermaid live-rendering in the viewer), please open an issue first to discuss the shape of the change.

## Credits

The HTML viewer's structure (FileSystem Access API, IndexedDB-persisted file handles, project-root directory walk for relative links) was adapted from the [`product-backlog`](https://github.com/photoenthu/product-backlog-skill) skill, which uses the same offline-first single-file pattern.
