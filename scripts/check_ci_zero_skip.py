#!/usr/bin/env python3
"""校验 CI JUnit XML 报告：确保默认离线门禁套件 0-Skip 且测试数 > 0。"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def main() -> int:
    xml_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("backend/pytest-ci.xml")
    if not xml_path.exists():
        print(f"ERROR: JUnit XML not found: {xml_path}", file=sys.stderr)
        return 1

    root = ET.parse(xml_path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    total = sum(int(s.attrib.get("tests", 0)) for s in suites)
    skipped = sum(int(s.attrib.get("skipped", 0)) for s in suites)
    failures = sum(int(s.attrib.get("failures", 0)) for s in suites)
    errors = sum(int(s.attrib.get("errors", 0)) for s in suites)

    print(
        f"CI JUnit Summary: tests={total}, failures={failures}, errors={errors}, skipped={skipped}"
    )
    if total == 0:
        print("FAIL: zero tests executed.", file=sys.stderr)
        return 1
    if skipped > 0:
        print(f"FAIL: {skipped} tests were skipped in CI core gate (must be 0).", file=sys.stderr)
        return 1
    if failures > 0 or errors > 0:
        return 1
    print("OK: 0-skip gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
