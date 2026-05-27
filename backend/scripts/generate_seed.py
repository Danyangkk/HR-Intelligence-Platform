#!/usr/bin/env python3
"""Regenerate seed JSON from frontend/index.html (SSOT)."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend" / "index.html"
OUT = Path(__file__).resolve().parents[1] / "src" / "seed" / "generated"


def parse_js_string_list(arr_text: str) -> list[str]:
    return re.findall(r"'([^']*)'", arr_text)


def parse_filters(filter_arr: str) -> list[dict]:
    return [{"field": a, "type": b} for a, b in re.findall(r"'([^']+)'\s*,\s*'([^']+)'", filter_arr)]


def parse_tpl_line(line: str) -> tuple[str, dict] | None:
    m = re.match(r"'(l3-[^']+)': t\((.+)\),?$", line.rstrip(","))
    if not m:
        return None
    lid = m.group(1)
    inner = m.group(2)
    groups: list[str] = []
    depth = 0
    start = None
    for i, ch in enumerate(inner):
        if ch == "[":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0 and start is not None:
                groups.append(inner[start : i + 1])
                start = None
    cols = parse_js_string_list(groups[0])
    filters = parse_filters(groups[1]) if len(groups) >= 2 else []
    keys = parse_js_string_list(groups[2]) if len(groups) >= 3 else [cols[0]]
    return lid, {"columns": cols, "filters": filters, "unique_key": keys}


def main() -> None:
    html = FRONTEND.read_text(encoding="utf-8")
    tree = re.search(r"const categoryTree = (\[[\s\S]*?\n\]);", html).group(1)
    tree = re.sub(r"(\w+):", r'"\1":', tree).replace("'", '"')
    tree = re.sub(r",\s*]", "]", tree)
    tree = re.sub(r",\s*}", "}", tree)
    categories = json.loads(tree)

    start = html.index("const TPL = {")
    end = html.index("\n};", start)
    block = html[start:end]
    tpl: dict[str, dict] = {}
    for line in block.split("\n"):
        line = line.strip()
        if not line or line in ("const TPL = {", "};"):
            continue
        if line.startswith("TPL["):
            m = re.match(r"TPL\['([^']+)'\]=TPL\['([^']+)'\]", line)
            if m and m.group(2) in tpl:
                tpl[m.group(1)] = json.loads(json.dumps(tpl[m.group(2)]))
            continue
        parsed = parse_tpl_line(line.rstrip(","))
        if parsed:
            tpl[parsed[0]] = parsed[1]

    feishu = sorted(
        re.search(r"const FEISHU = new Set\(\[(.*?)\]\)", html, re.S)
        .group(1)
        .replace("'", "")
        .replace(" ", "")
        .split(",")
    )
    doc_report = sorted(
        re.search(r"const DOC_REPORT = new Set\(\[(.*?)\]\)", html, re.S)
        .group(1)
        .replace("'", "")
        .replace(" ", "")
        .split(",")
    )

    OUT.mkdir(parents=True, exist_ok=True)
    OUT.joinpath("categories.json").write_text(json.dumps(categories, ensure_ascii=False, indent=2), encoding="utf-8")
    OUT.joinpath("templates.json").write_text(json.dumps(tpl, ensure_ascii=False, indent=2), encoding="utf-8")
    OUT.joinpath("feishu.json").write_text(json.dumps(feishu, ensure_ascii=False, indent=2), encoding="utf-8")
    OUT.joinpath("doc_report.json").write_text(json.dumps(doc_report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"generated: l3 tree + templates={len(tpl)} feishu={len(feishu)} report={len(doc_report)}")


if __name__ == "__main__":
    main()
