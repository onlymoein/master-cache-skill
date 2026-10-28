#!/usr/bin/env python3
"""Lint the caching-strategy skill against the Agent Skills spec and this repo's conventions.

Usage:
    python tools/lint_skill.py [skills/caching-strategy] [--json]

Checks
    frontmatter   only the six portable fields; name/description/compatibility/metadata rules;
                  plain YAML scalars that parse the same everywhere
    SKILL.md      <= 500 lines; every reference file linked; every local link resolves
    references    title, "Last reviewed" date, "When to read this", "Sources" with links,
                  "Contents" when > 100 lines (matching the ## headings), language tag on code fences
    paths         every assets/... and scripts/... path mentioned anywhere exists
    scripts       detect_stack.REFERENCES matches the files on disk; every script answers --help
    evals         evals/evals.json and evals/trigger_queries.json are well-formed (when present)
    size          skill folder < 30 MB (Skills API limit)

Exit 0 when there are no errors (warnings allowed), 1 otherwise. Standard library only.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ALLOWED_FIELDS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
FENCE_RE = re.compile(r"^(\s*)(`{3,}|~{3,})(.*)$")
PATH_RE = re.compile(r"(?<![\w/.-])((?:assets|scripts|references)/[A-Za-z0-9_./\[\]-]+\.[A-Za-z0-9]+)")


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, where: str, msg: str) -> None:
        self.errors.append(f"{where}: {msg}")

    def warn(self, where: str, msg: str) -> None:
        self.warnings.append(f"{where}: {msg}")


# --------------------------------------------------------------------------- frontmatter


def parse_frontmatter(text: str, rep: Report) -> tuple[dict, str]:
    if not text.startswith("---\n"):
        rep.error("SKILL.md", "must start with '---' frontmatter")
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        rep.error("SKILL.md", "frontmatter is not closed with '---'")
        return {}, text
    block, body = text[4:end], text[end + 5:]
    data: dict = {}
    current: str | None = None
    for i, line in enumerate(block.splitlines(), 2):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith((" ", "\t")):
            if current is None or not isinstance(data.get(current), dict):
                rep.error("SKILL.md", f"frontmatter line {i}: unexpected indentation")
                continue
            m = re.match(r"^\s+([A-Za-z0-9_-]+):\s*(.*)$", line)
            if not m:
                rep.error("SKILL.md", f"frontmatter line {i}: expected 'key: value' inside {current}")
                continue
            data[current][m.group(1)] = scalar(m.group(2), f"frontmatter line {i}", rep)
            continue
        m = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if not m:
            rep.error("SKILL.md", f"frontmatter line {i}: expected 'key: value'")
            continue
        key, value = m.group(1), m.group(2)
        current = key
        data[key] = {} if value == "" else scalar(value, f"frontmatter line {i}", rep)
    return data, body


def scalar(value: str, where: str, rep: Report) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    if value[:1] in set("[]{}&*!|>%@`#,?-") or ": " in value or " #" in value:
        rep.error("SKILL.md", f"{where}: quote this value; as a plain YAML scalar it won't parse the same everywhere")
    return value


def check_frontmatter(fm: dict, skill_dir: Path, rep: Report) -> None:
    for key in fm:
        if key not in ALLOWED_FIELDS:
            rep.error("SKILL.md", f"frontmatter field '{key}' is not portable (allowed: {', '.join(sorted(ALLOWED_FIELDS))})")
    name = fm.get("name")
    if not isinstance(name, str) or not name:
        rep.error("SKILL.md", "frontmatter needs a name")
    else:
        if not NAME_RE.match(name) or len(name) > 64:
            rep.error("SKILL.md", "name must be lowercase letters, digits and single hyphens, <= 64 chars")
        if name != skill_dir.name:
            rep.error("SKILL.md", f"name '{name}' must match the directory '{skill_dir.name}'")
        if "claude" in name or "anthropic" in name:
            rep.error("SKILL.md", "name must not contain 'claude' or 'anthropic'")
    desc = fm.get("description")
    if not isinstance(desc, str) or not desc.strip():
        rep.error("SKILL.md", "frontmatter needs a description")
    else:
        if len(desc) > 1024:
            rep.error("SKILL.md", f"description is {len(desc)} chars; max 1024")
        if re.search(r"<[a-zA-Z/]", desc):
            rep.error("SKILL.md", "description must not contain XML/HTML tags")
        if "use when" not in desc.lower():
            rep.warn("SKILL.md", "description should say when to use the skill ('Use when ...')")
    compat = fm.get("compatibility")
    if compat is not None and (not isinstance(compat, str) or len(compat) > 500):
        rep.error("SKILL.md", "compatibility must be a string of at most 500 chars")
    meta = fm.get("metadata")
    if meta is not None:
        if not isinstance(meta, dict) or not all(isinstance(v, str) for v in meta.values()):
            rep.error("SKILL.md", "metadata must map strings to strings")
        else:
            reviewed = meta.get("last-reviewed")
            if reviewed:
                try:
                    age = (dt.date.today() - dt.date.fromisoformat(reviewed)).days
                    if age > 180:
                        rep.warn("SKILL.md", f"last-reviewed is {age} days old; run the quarterly content review")
                except ValueError:
                    rep.error("SKILL.md", "metadata.last-reviewed must be YYYY-MM-DD")


# --------------------------------------------------------------------------- markdown checks


def fences_ok(path: Path, text: str, rep: Report) -> None:
    open_fence: str | None = None
    for i, line in enumerate(text.splitlines(), 1):
        m = FENCE_RE.match(line)
        if not m:
            continue
        marker, info = m.group(2), m.group(3).strip()
        if open_fence is None:
            open_fence = marker
            if not info:
                rep.error(rel(path), f"line {i}: code fence without a language tag")
        elif marker.startswith(open_fence[0]) and len(marker) >= len(open_fence) and not info:
            open_fence = None
    if open_fence is not None:
        rep.error(rel(path), "unclosed code fence")


def check_reference(path: Path, rep: Report) -> None:
    text = path.read_text()
    lines = text.splitlines()
    where = rel(path)
    if not lines or not lines[0].startswith("# "):
        rep.error(where, "must start with a '# Title' line")
    if not re.search(r"^Last reviewed: \d{4}-\d{2}-\d{2}", text, re.M):
        rep.error(where, "needs a 'Last reviewed: YYYY-MM-DD' line")
    headings = re.findall(r"^## (.+)$", text, re.M)
    if "When to read this" not in headings:
        rep.error(where, "needs a '## When to read this' section")
    if "Sources" not in headings:
        rep.error(where, "needs a '## Sources' section")
    else:
        sources = text.split("\n## Sources", 1)[1]
        links = re.findall(r"\]\((https?://[^)]+)\)", sources)
        if not links:
            rep.error(where, "Sources has no links")
        elif len(links) < 3:
            rep.warn(where, f"Sources has {len(links)} link(s); aim for 3-12 primary sources")
        elif len(links) > 12:
            rep.warn(where, f"Sources has {len(links)} links; keep 3-12")
    if len(lines) > 100:
        if "Contents" not in headings:
            rep.error(where, f"{len(lines)} lines: needs a '## Contents' section")
        else:
            block = text.split("## Contents", 1)[1].split("\n## ", 1)[0]
            listed = [re.sub(r"^\[|\]\(.*\)$", "", x.strip()) for x in re.findall(r"^\s*-\s+(.+)$", block, re.M)]
            actual = [h for h in headings if h != "Contents"]
            if listed != actual:
                missing = [h for h in actual if h not in listed]
                extra = [h for h in listed if h not in actual]
                rep.error(where, f"Contents doesn't match the ## headings (missing {missing}, extra {extra})")
    if len(lines) > 400:
        rep.warn(where, f"{len(lines)} lines; references should stay focused (80-350)")
    fences_ok(path, text, rep)


def rel(path: Path) -> str:
    try:
        return path.relative_to(REPO).as_posix()
    except ValueError:
        return str(path)


def mentioned_paths(text: str) -> set[str]:
    out = set()
    for m in PATH_RE.finditer(text):
        p = m.group(1).rstrip(".,;:")
        if "{" in p or "*" in p or "<" in p:
            continue
        out.add(p)
    return out


# --------------------------------------------------------------------------- main


def lint(skill_dir: Path) -> Report:
    rep = Report()
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        rep.error(rel(skill_dir), "missing SKILL.md")
        return rep
    text = skill_md.read_text()
    fm, body = parse_frontmatter(text, rep)
    check_frontmatter(fm, skill_dir, rep)
    n_lines = len(text.splitlines())
    if n_lines > 500:
        rep.error("SKILL.md", f"{n_lines} lines; keep SKILL.md under 500")
    if len(body) / 4 > 5000:
        rep.warn("SKILL.md", f"body is ~{int(len(body) / 4)} tokens; only the first ~5000 survive compaction")
    fences_ok(skill_md, text, rep)

    references = sorted(p for p in (skill_dir / "references").rglob("*.md"))
    ref_paths = [p.relative_to(skill_dir).as_posix() for p in references]
    for rp in ref_paths:
        if f"({rp})" not in body and rp not in body:
            rep.error("SKILL.md", f"does not link {rp} (every reference must be one link from SKILL.md)")
    for target in re.findall(r"\]\(([^)#]+)\)", body):
        if not target.startswith(("http://", "https://", "mailto:")) and not (skill_dir / target).exists():
            rep.error("SKILL.md", f"broken link {target}")
    for path in references:
        check_reference(path, rep)

    # Every assets/ and scripts/ path mentioned anywhere in the skill must exist.
    for path in [skill_md, *references, *sorted((skill_dir / "assets").rglob("*.md")),
                 *sorted((skill_dir / "scripts").glob("*.py"))]:
        for p in mentioned_paths(path.read_text()):
            if p.startswith("references/") and p.endswith(".md") and not (skill_dir / p).exists():
                rep.error(rel(path), f"mentions missing file {p}")
            elif p.startswith(("assets/", "scripts/")) and not (skill_dir / p).exists():
                rep.error(rel(path), f"mentions missing file {p}")

    # detect_stack.REFERENCES must match the files on disk.
    proc = subprocess.run([sys.executable, str(skill_dir / "scripts" / "detect_stack.py"), "--list-references"],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        rep.error("scripts/detect_stack.py", "--list-references failed")
    else:
        listed = set(json.loads(proc.stdout))
        for missing in sorted(set(ref_paths) - listed):
            rep.error("scripts/detect_stack.py", f"REFERENCES lacks {missing}")
        for extra in sorted(listed - set(ref_paths)):
            rep.error("scripts/detect_stack.py", f"REFERENCES lists missing file {extra}")
    for script in sorted((skill_dir / "scripts").glob("*.py")):
        proc = subprocess.run([sys.executable, str(script), "--help"], capture_output=True, text=True)
        if proc.returncode != 0 or "usage" not in proc.stdout.lower():
            rep.error(rel(script), "--help must print usage and exit 0")
        head = script.read_text()[:2000]
        if '"""' not in head:
            rep.warn(rel(script), "add a module docstring describing usage and output")

    total = sum(p.stat().st_size for p in skill_dir.rglob("*") if p.is_file())
    if total > 30 * 1024 * 1024:
        rep.error(rel(skill_dir), f"skill is {total / 1e6:.1f} MB; the Skills API limit is 30 MB")
    for junk in list(skill_dir.rglob("__pycache__")) + list(skill_dir.rglob(".DS_Store")):
        rep.warn(rel(junk), "remove before packaging")

    lint_evals(rep)
    return rep


def lint_evals(rep: Report) -> None:
    evals = REPO / "evals" / "evals.json"
    if evals.exists():
        try:
            data = json.loads(evals.read_text())
        except ValueError as exc:
            rep.error("evals/evals.json", f"invalid JSON: {exc}")
            return
        if data.get("skill_name") != "caching-strategy":
            rep.error("evals/evals.json", "skill_name must be caching-strategy")
        ids = set()
        for case in data.get("evals", []):
            cid = case.get("id")
            if cid in ids:
                rep.error("evals/evals.json", f"duplicate eval id {cid}")
            ids.add(cid)
            for field in ("id", "prompt", "expected_output", "expectations"):
                if not case.get(field):
                    rep.error("evals/evals.json", f"eval {cid}: missing {field}")
            for f in case.get("files", []):
                if not (REPO / "evals" / f).exists():
                    rep.error("evals/evals.json", f"eval {cid}: missing file {f}")
        if len(ids) < 3:
            rep.error("evals/evals.json", "needs at least 3 evals")
    triggers = REPO / "evals" / "trigger_queries.json"
    if triggers.exists():
        try:
            items = json.loads(triggers.read_text())
        except ValueError as exc:
            rep.error("evals/trigger_queries.json", f"invalid JSON: {exc}")
            return
        pos = sum(1 for q in items if q.get("should_trigger") is True)
        neg = sum(1 for q in items if q.get("should_trigger") is False)
        if pos < 8 or neg < 8:
            rep.error("evals/trigger_queries.json", f"needs >= 8 positive and >= 8 negative queries (has {pos}/{neg})")
        for q in items:
            if q.get("split") not in ("train", "validation") or not q.get("query"):
                rep.error("evals/trigger_queries.json", f"bad entry {q}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lint the caching-strategy skill.")
    parser.add_argument("skill_dir", nargs="?", default=str(REPO / "skills" / "caching-strategy"))
    parser.add_argument("--json", action="store_true", help="print a JSON report")
    args = parser.parse_args(argv)
    rep = lint(Path(args.skill_dir).resolve())
    if args.json:
        json.dump({"errors": rep.errors, "warnings": rep.warnings}, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        for w in rep.warnings:
            print(f"warning: {w}")
        for e in rep.errors:
            print(f"error: {e}")
        print(f"{len(rep.errors)} error(s), {len(rep.warnings)} warning(s)")
    return 1 if rep.errors else 0


if __name__ == "__main__":
    sys.exit(main())
