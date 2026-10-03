#!/usr/bin/env python3
"""Synchronize the static site's auditable synthetic fixtures; no network required."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def outputs():
    data = {}
    files = {}
    for language in ("zh-CN", "en"):
        data[language] = json.loads((ROOT / "examples/preview" / f"demo.{language}.json").read_text(encoding="utf-8"))
        for extension in ("html", "txt", "json", "ris", "bib"):
            name = f"demo.{language}.{extension}"
            files[ROOT / "docs/preview" / name] = (ROOT / "examples/preview" / name).read_bytes()
    text = "/* Fixed synthetic samples copied from examples/preview; no network data. */\nwindow.PAPER_TRACKER_DEMO = "
    text += json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n"
    files[ROOT / "docs/assets/fixtures.js"] = text.encode("utf-8")
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check fixtures without writing")
    args = parser.parse_args()
    stale = []
    for target, expected in outputs().items():
        if args.check:
            if not target.exists() or target.read_bytes() != expected:
                stale.append(str(target.relative_to(ROOT)))
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(expected)
    if stale:
        parser.exit(1, "Stale demo assets; run python scripts/build_demo_site.py:\n" + "\n".join(stale) + "\n")
    print("Static demo fixtures verified." if args.check else "Static demo fixtures synchronized.")


if __name__ == "__main__":
    main()
