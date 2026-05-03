#!/usr/bin/env python3
"""Deterministic helpers for the user-manual skill.

The skill itself does the heavy lifting (reading artifacts, writing prose,
elaborating jargon, fortifying with web search) — this script handles the
few primitives that are easy to get wrong in prose:

  * `now-et`                          — current timestamp in `YYYY-MM-DD HH:MM ET`
  * `init <md-path>`                  — create the empty manual scaffold if missing
  * `scan-artifacts <project-root>`   — list every superpowers artifact with a
                                        sha256 of its content (JSON to stdout)
  * `parse-citations <md-path>`       — read the existing manual's Citations
                                        table and emit the path -> hash mapping
                                        as JSON
  * `diff-artifacts <project-root> <md-path>`
                                      — combine the two: tell the skill which
                                        artifacts are NEW (not yet cited),
                                        CHANGED (cited but content changed),
                                        UNCHANGED (skip), or MISSING (cited
                                        but file no longer on disk)
  * `html-template-version`           — print the bundled template version
  * `regenerate-html-if-stale <html-path>`
        — write the bundled HTML template to the path if the file is missing
          or its embedded version is older than the template's. No-ops
          otherwise. Prints `created` / `regenerated` / `unchanged`.

Pure stdlib. Python 3.9+ (zoneinfo).

Invoke as `python3 manual_helper.py <subcommand> [args]`.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
HTML_VERSION_RE = re.compile(r"<!--\s*user-manual-dashboard-version:\s*(\d+)\s*-->")
TEMPLATE_HTML_PATH = Path(__file__).resolve().parent.parent / "templates" / "user-manual.html"

# The four superpowers subdirectories the skill knows about. Order matters
# only for human-readability of the scan output.
SUPERPOWERS_KINDS = ("specs", "plans", "findings", "reviews")

TEMPLATE = """# User Manual

_Maintained by the [`user-manual`](https://github.com/photoenthu/user-manual-skill) skill. Generated and updated from the project's `docs/superpowers/` artifacts. Re-run the skill after writing new specs / plans / findings / reviews to fold them in._

> **Manual status:** scaffold only. Run the `user-manual` skill to populate this file from the project's superpowers artifacts.

## Quick Start

_Will be populated by the skill on its first real run._

## Concepts and Glossary

_Will be populated by the skill on its first real run._

## Daily Usage

_Will be populated by the skill on its first real run._

## Configuration

_Will be populated by the skill on its first real run._

## Troubleshooting and FAQ

_Will be populated by the skill on its first real run._

## Architecture and Internals

_Will be populated by the skill on its first real run._

## Citations

### Project artifacts

This table is the skill's idempotency ledger. Every superpowers artifact the
skill has folded into the manual appears here with a content hash. On the next
run, artifacts whose hash matches this table are skipped; new or changed
artifacts are processed.

| Path | Kind | Title | SHA256 (content) | First cited (ET) | Last seen (ET) |
|---|---|---|---|---|---|

### External references

Web pages and external docs the skill cited while fortifying the manual. Not
used for idempotency — the skill may re-fetch these on future runs to keep
elaborations current.

| URL | Title | Cited from section | Last fetched (ET) |
|---|---|---|---|
"""

# Pulled out so callers can verify the exact section header before parsing.
CITATIONS_HEADING = "## Citations"
ARTIFACTS_SUBHEADING = "### Project artifacts"
EXTERNAL_SUBHEADING = "### External references"


def now_et() -> str:
    return datetime.now(ET).strftime("%Y-%m-%d %H:%M ET")


def init(path: Path) -> bool:
    """Create the scaffold file if missing. Returns True if it created it."""
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(TEMPLATE, encoding="utf-8")
    return True


# ---------- Artifact scanning ----------

def _short_hash(content: bytes) -> str:
    """Truncated sha256 — full hash is overkill for citation tracking and
    bloats the table visually. 16 hex chars (64 bits) is collision-resistant
    enough for a per-project artifact set."""
    return hashlib.sha256(content).hexdigest()[:16]


def _extract_title(text: str, fallback: str) -> str:
    """Best-effort H1 extraction from a markdown file. Falls back to the
    filename stem when no H1 is found in the first ~20 lines."""
    for line in text.splitlines()[:20]:
        stripped = line.strip()
        if stripped.startswith("# ") and not stripped.startswith("## "):
            return stripped[2:].strip()
    return fallback


def scan_artifacts(project_root: Path) -> list[dict]:
    """Walk `<project-root>/docs/superpowers/{kind}/` and return one dict per
    artifact:
        {
          "path": "docs/superpowers/plans/2026-04-27-foo.md",
          "kind": "plan",
          "title": "Regime-router foundation",
          "hash": "a1b2c3d4e5f60718",
          "size": 12048
        }
    Sorted by (kind, path) for stable output across runs."""
    base = project_root / "docs" / "superpowers"
    out: list[dict] = []
    if not base.exists():
        return out
    for kind in SUPERPOWERS_KINDS:
        kind_dir = base / kind
        if not kind_dir.is_dir():
            continue
        for path in sorted(kind_dir.glob("*.md")):
            try:
                raw = path.read_bytes()
                text = raw.decode("utf-8", errors="replace")
            except OSError:
                continue
            rel = path.relative_to(project_root).as_posix()
            out.append({
                "path": rel,
                # Singular: "plan", "spec", etc. — reads better in the citation table.
                "kind": kind.rstrip("s") if kind != "specs" else "spec",
                "title": _extract_title(text, path.stem),
                "hash": _short_hash(raw),
                "size": len(raw),
            })
    return out


# ---------- Citation parsing ----------

def _split_table_row(line: str) -> list[str]:
    """`\\|` -> literal `|` inside a cell, `|` is the column separator. Same
    convention the markdown table uses; mirrors the JS parser in the dashboard."""
    cells: list[str] = []
    buf: list[str] = []
    i = 0
    while i < len(line):
        c = line[i]
        if c == "\\" and i + 1 < len(line) and line[i + 1] == "|":
            buf.append("|")
            i += 2
            continue
        if c == "|":
            cells.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(c)
        i += 1
    cells.append("".join(buf))
    if cells and cells[0].strip() == "":
        cells.pop(0)
    if cells and cells[-1].strip() == "":
        cells.pop()
    return [c.strip() for c in cells]


def _is_separator_row(cells: list[str]) -> bool:
    return bool(cells) and all(re.match(r"^:?-+:?$", c) for c in cells)


def parse_citations(path: Path) -> dict:
    """Read the existing manual and pull out:
        {
          "artifacts": [{path, kind, title, hash, first_cited, last_seen}, ...],
          "external":  [{url, title, section, last_fetched}, ...]
        }
    Returns empty lists for both if the file is missing or the Citations
    section isn't there yet (e.g., scaffold-only manual)."""
    result = {"artifacts": [], "external": []}
    if not path.exists():
        return result
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    # Find the Citations section first; everything before it is irrelevant.
    cite_idx = None
    for idx, line in enumerate(lines):
        if line.strip() == CITATIONS_HEADING:
            cite_idx = idx
            break
    if cite_idx is None:
        return result

    # Now sub-walk: find each known subheading and collect table rows under it
    # until the next `## ` (or `### `, but only if it's a sibling we don't recognize).
    sub_idx = {ARTIFACTS_SUBHEADING: None, EXTERNAL_SUBHEADING: None}
    for idx in range(cite_idx + 1, len(lines)):
        stripped = lines[idx].strip()
        if stripped.startswith("## ") and stripped != CITATIONS_HEADING:
            break  # Left the Citations section entirely.
        if stripped in sub_idx:
            sub_idx[stripped] = idx

    def _collect_rows(start_idx: int | None) -> list[list[str]]:
        if start_idx is None:
            return []
        rows: list[list[str]] = []
        seen_separator = False
        for idx in range(start_idx + 1, len(lines)):
            line = lines[idx]
            stripped = line.strip()
            if stripped.startswith("## ") or stripped.startswith("### "):
                break
            if not stripped.startswith("|"):
                continue
            cells = _split_table_row(line)
            if _is_separator_row(cells):
                seen_separator = True
                continue
            if not seen_separator:
                # This is the header row; skip it.
                continue
            rows.append(cells)
        return rows

    for cells in _collect_rows(sub_idx[ARTIFACTS_SUBHEADING]):
        if len(cells) < 6:
            continue
        path_cell, kind_cell, title_cell, hash_cell, first_cell, last_cell = cells[:6]
        # The path may be wrapped in a markdown link: `[label](path)` — recover
        # the bare path. Prefer the link target when present.
        m = re.match(r"^\[(?P<label>[^\]]+)\]\((?P<target>[^)]+)\)$", path_cell)
        bare_path = m.group("target") if m else path_cell
        # The hash cell may be wrapped in inline-code backticks — strip them.
        bare_hash = hash_cell.strip("`")
        result["artifacts"].append({
            "path": bare_path,
            "kind": kind_cell,
            "title": title_cell,
            "hash": bare_hash,
            "first_cited": first_cell,
            "last_seen": last_cell,
        })

    for cells in _collect_rows(sub_idx[EXTERNAL_SUBHEADING]):
        if len(cells) < 4:
            continue
        url_cell, title_cell, section_cell, fetched_cell = cells[:4]
        m = re.match(r"^\[(?P<label>[^\]]+)\]\((?P<target>[^)]+)\)$", url_cell)
        bare_url = m.group("target") if m else url_cell
        result["external"].append({
            "url": bare_url,
            "title": title_cell,
            "section": section_cell,
            "last_fetched": fetched_cell,
        })

    return result


# ---------- Diff: which artifacts need processing on this run? ----------

def diff_artifacts(project_root: Path, manual_path: Path) -> dict:
    """Compare on-disk superpowers artifacts against the manual's existing
    citation table. Returns four buckets:
        {
          "new":       [scan_entry, ...],   # not in citations at all
          "changed":   [scan_entry, ...],   # cited but hash changed
          "unchanged": [scan_entry, ...],   # cited and hash matches (skip)
          "missing":   [citation_entry, ...]  # cited but file is gone
        }
    Each scan_entry has the same shape as `scan-artifacts` output. Missing
    entries are the citation rows themselves (no on-disk presence)."""
    scanned = scan_artifacts(project_root)
    cited = parse_citations(manual_path)["artifacts"]
    cited_by_path = {c["path"]: c for c in cited}
    scanned_paths = {s["path"] for s in scanned}

    new: list[dict] = []
    changed: list[dict] = []
    unchanged: list[dict] = []
    for entry in scanned:
        prior = cited_by_path.get(entry["path"])
        if prior is None:
            new.append(entry)
        elif prior["hash"] != entry["hash"]:
            changed.append(entry)
        else:
            unchanged.append(entry)

    missing = [c for c in cited if c["path"] not in scanned_paths]

    return {"new": new, "changed": changed, "unchanged": unchanged, "missing": missing}


# ---------- HTML template versioning (mirrors product-backlog skill) ----------

def _read_html_version(text: str) -> int | None:
    match = HTML_VERSION_RE.search(text)
    return int(match.group(1)) if match else None


def html_template_version() -> int:
    if not TEMPLATE_HTML_PATH.exists():
        raise FileNotFoundError(
            f"bundled HTML template missing at {TEMPLATE_HTML_PATH}"
        )
    version = _read_html_version(TEMPLATE_HTML_PATH.read_text(encoding="utf-8"))
    if version is None:
        raise ValueError(
            f"template at {TEMPLATE_HTML_PATH} has no "
            f"<!-- user-manual-dashboard-version: N --> marker"
        )
    return version


def regenerate_html_if_stale(html_path: Path) -> str:
    template_version = html_template_version()
    html_path.parent.mkdir(parents=True, exist_ok=True)

    if not html_path.exists():
        shutil.copyfile(TEMPLATE_HTML_PATH, html_path)
        return "created"

    existing_version = _read_html_version(html_path.read_text(encoding="utf-8"))
    if existing_version is None or existing_version < template_version:
        shutil.copyfile(TEMPLATE_HTML_PATH, html_path)
        return "regenerated"

    return "unchanged"


# ---------- CLI ----------

def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2

    cmd = argv[1]

    if cmd == "now-et":
        print(now_et())
        return 0

    if cmd == "init":
        if len(argv) != 3:
            print("usage: manual_helper.py init <md-path>", file=sys.stderr)
            return 2
        target = Path(argv[2])
        created = init(target)
        print(f"{'created' if created else 'exists'}: {target}")
        return 0

    if cmd == "scan-artifacts":
        if len(argv) != 3:
            print("usage: manual_helper.py scan-artifacts <project-root>", file=sys.stderr)
            return 2
        entries = scan_artifacts(Path(argv[2]))
        json.dump(entries, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    if cmd == "parse-citations":
        if len(argv) != 3:
            print("usage: manual_helper.py parse-citations <md-path>", file=sys.stderr)
            return 2
        result = parse_citations(Path(argv[2]))
        json.dump(result, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    if cmd == "diff-artifacts":
        if len(argv) != 4:
            print("usage: manual_helper.py diff-artifacts <project-root> <md-path>", file=sys.stderr)
            return 2
        result = diff_artifacts(Path(argv[2]), Path(argv[3]))
        json.dump(result, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    if cmd == "html-template-version":
        print(html_template_version())
        return 0

    if cmd == "regenerate-html-if-stale":
        if len(argv) != 3:
            print(
                "usage: manual_helper.py regenerate-html-if-stale <html-path>",
                file=sys.stderr,
            )
            return 2
        result = regenerate_html_if_stale(Path(argv[2]))
        print(f"{result}: {argv[2]}")
        return 0

    print(f"unknown subcommand: {cmd}", file=sys.stderr)
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
