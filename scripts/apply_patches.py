#!/usr/bin/env python3
"""Apply exact-match source patches to a checked-out openai/codex tree.

Every patch file in `patches/` is JSON:

    {
      "name": "reconnect",
      "description": "Adds the [reconnect] config table: fixed or default reconnect interval, and a stream retry budget override.",
      "edits": [
        {"file": "codex-rs/...", "find": "...", "replace": "...", "expect": 1},
        {"file": "codex-rs/...", "create": true, "replace": "<full file content>"}
      ]
    }

An edit only applies when `find` occurs exactly `expect` times in the target
file. Any mismatch (missing, or hit count differs) aborts the whole run before
anything is written, so an upstream refactor fails the build loudly instead of
leaving a half-patched tree. An edit with `"create": true` writes a brand new
file instead, and fails if the file already exists.

Usage:
    python scripts/apply_patches.py --root codex-src           # apply
    python scripts/apply_patches.py --root codex-src --check   # dry run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PATCH_DIR = Path(__file__).resolve().parents[1] / "patches"


def load_patches() -> list[dict]:
    patch_files = sorted(PATCH_DIR.glob("*.json"))
    if not patch_files:
        raise SystemExit(f"error: no patch files found in {PATCH_DIR}")

    patches: list[dict] = []
    for patch_file in patch_files:
        data = json.loads(patch_file.read_text(encoding="utf-8"))
        if not isinstance(data.get("edits"), list) or not data["edits"]:
            raise SystemExit(f"error: {patch_file.name} has no edits")
        for edit in data["edits"]:
            if edit.get("create"):
                missing = [key for key in ("file", "replace") if key not in edit]
                if missing:
                    raise SystemExit(f"error: {patch_file.name} create edit missing {missing}")
                if "find" in edit:
                    raise SystemExit(
                        f"error: {patch_file.name} create edit must not have a find anchor"
                    )
                continue
            missing = [key for key in ("file", "find", "replace") if key not in edit]
            if missing:
                raise SystemExit(f"error: {patch_file.name} edit missing {missing}")
        patches.append(data)
    return patches


def read_text(path: Path) -> tuple[str, str]:
    """Return (text with LF newlines, newline style to restore on write)."""
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    newline = "\r\n" if "\r\n" in text else "\n"
    return text.replace("\r\n", "\n"), newline


def apply_edit(text: str, edit: dict) -> str:
    find = edit["find"]
    expect = edit.get("expect", 1)
    count = text.count(find)
    if count != expect:
        raise SystemExit(
            "error: patch anchor mismatch\n"
            f"  file:   {edit['file']}\n"
            f"  expect: {expect} occurrence(s)\n"
            f"  found:  {count}\n"
            f"  anchor: {find.splitlines()[0][:120]!r}"
        )
    if edit["replace"] in text:
        raise SystemExit(
            f"error: replacement already present in {edit['file']}; "
            "is the tree already patched?"
        )
    return text.replace(find, edit["replace"], expect)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        default=".",
        help="root of the openai/codex checkout to patch (default: cwd)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify every anchor matches without writing any file",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not (root / "codex-rs").is_dir():
        raise SystemExit(f"error: {root} does not look like a codex checkout")

    patches = load_patches()
    texts: dict[Path, str] = {}
    newlines: dict[Path, str] = {}
    applied = 0
    for patch in patches:
        print(f"patch: {patch.get('name', '?')} ({len(patch['edits'])} edits)")
        for edit in patch["edits"]:
            target = root / edit["file"]
            if edit.get("create"):
                if target in texts or target.exists():
                    raise SystemExit(f"error: create target already exists {edit['file']}")
                texts[target] = edit["replace"]
                newlines[target] = "\n"
                applied += 1
                print(f"  new {edit['file']}")
                continue
            if target not in texts:
                if not target.is_file():
                    raise SystemExit(f"error: missing file {edit['file']}")
                texts[target], newlines[target] = read_text(target)
            texts[target] = apply_edit(texts[target], edit)
            applied += 1
            first = edit["find"].splitlines()[0]
            print(f"  ok  {edit['file']}  <- {first[:90]!r}")

    if args.check:
        print(f"check passed: {applied} anchors matched, no files written")
        return 0

    for target, text in texts.items():
        if newlines[target] == "\r\n":
            text = text.replace("\n", "\r\n")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="")
        print(f"  wrote {target.relative_to(root)}")
    print(f"applied {applied} edits across {len(texts)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
