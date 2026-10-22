#!/usr/bin/env python3
"""Independent validation of the public eSkillz knowledge bundle.

This script runs in the PUBLIC repository and deliberately does not share
code with the private tooling, so a defect in the private export cannot also
hide itself from this check. It needs only PyYAML.

Checks:
  * OKF v0.2 conformance (frontmatter with non-empty `type`; index/log rules)
  * no private governance metadata or private source references
  * every internal link resolves inside the bundle
  * no hidden HTML comments
  * no credential or sensitive-data patterns
  * publication.json lists exactly the concepts present, with provenance
  * repository foundation: required files, rights notice, manifest
    consistency, no unexpected top-level files, no individual reviewer
    identities

Usage: python tools/validate_public.py [repository-root]
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import yaml

REQUIRED_FILES = [
    "README.md", "MANIFEST.yaml", "AGENTS.md", "llms.txt", "publication.json",
    "knowledge/index.md", "knowledge/log.md", "tools/validate_public.py",
    ".github/workflows/validate.yml",
]
ALLOWED_TOP_LEVEL = {
    ".git", ".github", ".gitignore", "knowledge", "tools", "README.md", "MANIFEST.yaml",
    "AGENTS.md", "llms.txt", "publication.json", "LICENSE", "NOTICE", "SECURITY.md",
}
PUBLIC_HUMAN_ACTOR = "human:eskillz"
PRIVATE_KEYS = {"visibility", "approval", "owner", "risk", "publish", "effective", "authoritative_system"}
FRONTMATTER_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL)
FENCE_RE = re.compile(r"^(```|~~~).*?^\1[ \t]*$", re.DOTALL | re.MULTILINE)
LINK_RE = re.compile(r"!?\[[^\]\n]*\]\((<[^>\n]+>|[^)\s]+)(?:\s+\"[^\"]*\")?\)")
SECRET_RE = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY|\b(?:AKIA|ASIA)[0-9A-Z]{16}\b|\bgh[pousr]_[A-Za-z0-9]{36,}"
    r"|\bgithub_pat_[A-Za-z0-9_]{40,}|\bxox[abposr]-[A-Za-z0-9-]{10,}|\bAIza[0-9A-Za-z_-]{35}\b"
    r"|\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{32,}|\b[rs]k_live_[0-9A-Za-z]{20,}"
)


class Loader(yaml.SafeLoader):
    pass


Loader.yaml_implicit_resolvers = {
    k: [(t, r) for t, r in v if t != "tag:yaml.org,2002:timestamp"]
    for k, v in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def check_foundation(root: Path, errors: list[str]) -> None:
    for rel in REQUIRED_FILES:
        if not (root / rel).is_file():
            errors.append(f"{rel}: required file is missing")
    for entry in sorted(p.name for p in root.iterdir()):
        if entry not in ALLOWED_TOP_LEVEL:
            errors.append(f"{entry}: unexpected top-level file; content arrives only through publication")
    readme = root / "README.md"
    if readme.is_file() and "All rights reserved" not in readme.read_text(encoding="utf-8"):
        errors.append("README.md: missing the 'All rights reserved' notice")
    manifest_path, index_path = root / "MANIFEST.yaml", root / "knowledge" / "index.md"
    if manifest_path.is_file() and index_path.is_file():
        manifest = yaml.load(manifest_path.read_text(encoding="utf-8"), Loader=Loader) or {}  # noqa: S506
        match = FRONTMATTER_RE.match(index_path.read_text(encoding="utf-8"))
        index_fm = (yaml.load(match.group(1), Loader=Loader) or {}) if match else {}  # noqa: S506
        if str((manifest.get("okf") or {}).get("version")) != str(index_fm.get("okf_version")):
            errors.append("MANIFEST.yaml: okf.version does not match knowledge/index.md okf_version")
    pub_path = root / "publication.json"
    if pub_path.is_file():
        pub = json.loads(pub_path.read_text(encoding="utf-8"))
        if not re.fullmatch(r"[0-9a-f]{40}", str(pub.get("source_commit", ""))):
            errors.append("publication.json: source_commit must be the full private source commit SHA")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", str(pub.get("published_at", ""))):
            errors.append("publication.json: published_at must be an ISO 8601 UTC timestamp")
        for key in ("okf_version", "source_repository", "concepts"):
            if key not in pub:
                errors.append(f"publication.json: missing {key}")


def main(root: Path) -> int:
    bundle = root / "knowledge"
    errors: list[str] = []
    concepts: dict[str, str] = {}

    if not bundle.is_dir():
        print("knowledge/ not found")
        return 1

    for path in sorted(bundle.rglob("*.md")):
        rel = path.relative_to(bundle).as_posix()
        text = path.read_text(encoding="utf-8")
        match = FRONTMATTER_RE.match(text)
        fm = None
        if match:
            try:
                fm = yaml.load(match.group(1), Loader=Loader) or {}  # noqa: S506
            except yaml.YAMLError as exc:
                errors.append(f"{rel}: invalid YAML frontmatter ({exc})")
                continue
        body = text[match.end():] if match else text

        if path.name == "index.md":
            if fm is not None and (rel != "index.md" or set(fm) - {"okf_version"}):
                errors.append(f"{rel}: index.md may only carry okf_version, at the bundle root")
        elif path.name == "log.md":
            dates = re.findall(r"^##\s+(.+?)\s*$", text, re.MULTILINE)
            if any(not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) for d in dates) or dates != sorted(dates, reverse=True):
                errors.append(f"{rel}: log headings must be ISO dates, newest first")
        else:
            if not isinstance(fm, dict) or not str(fm.get("type") or "").strip():
                errors.append(f"{rel}: concept needs YAML frontmatter with a non-empty type")
                continue
            leaked = PRIVATE_KEYS & set(fm)
            if leaked:
                errors.append(f"{rel}: private metadata present: {sorted(leaked)}")
            if fm.get("status", "stable") == "draft":
                errors.append(f"{rel}: draft concepts must not be published")
            actors = [fm.get("generated") or {}] + (fm.get("verified") if isinstance(fm.get("verified"), list)
                                                     else [fm.get("verified") or {}])
            for entry in actors:
                actor = str((entry or {}).get("by", "")) if isinstance(entry, dict) else ""
                if actor.startswith("human:") and actor != PUBLIC_HUMAN_ACTOR:
                    errors.append(f"{rel}: individual reviewer identity '{actor}' must not be published")
            concepts[rel[:-3]] = hashlib.sha256(text.encode("utf-8")).hexdigest()

        if "urn:eskillz:" in text:
            errors.append(f"{rel}: private eSkillz URN reference")
        if "<!--" in body and "Generated by tools/build_indexes.py" not in body:
            errors.append(f"{rel}: HTML comments are not allowed in public content")
        # log.md is history: it may legitimately mention concepts since withdrawn.
        targets = [] if path.name == "log.md" else LINK_RE.findall(FENCE_RE.sub("", body))
        for target in targets:
            target = target.strip("<>")
            if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target) or target.startswith("#"):
                continue
            clean = target.split("#", 1)[0]
            resolved = (bundle / clean.lstrip("/")) if clean.startswith("/") else (path.parent / clean)
            resolved = resolved.resolve()
            if bundle.resolve() not in resolved.parents and resolved != bundle.resolve():
                errors.append(f"{rel}: link leaves the bundle: {target}")
            elif not resolved.exists():
                errors.append(f"{rel}: broken link: {target}")

    for path in sorted(root.rglob("*")):
        if path.is_file() and ".git" not in path.parts and path.suffix in {".md", ".json", ".yaml", ".yml", ".txt"}:
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if SECRET_RE.search(line):
                    errors.append(f"{path.relative_to(root).as_posix()}:{n}: possible credential")

    check_foundation(root, errors)

    manifest_path = root / "publication.json"
    if manifest_path.exists():
        listed = json.loads(manifest_path.read_text(encoding="utf-8")).get("concepts", {})
        if set(listed) != set(concepts):
            errors.append("publication.json does not match the concepts in knowledge/")
        for cid, meta in listed.items():
            if cid in concepts and meta.get("sha256") != concepts[cid]:
                errors.append(f"{cid}.md: content differs from publication.json (edited outside the publishing process?)")
    elif concepts:
        errors.append("publication.json is missing")

    for e in errors:
        print(f"ERROR {e}")
    print(f"{len(concepts)} public concepts checked: {len(errors)} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent))
