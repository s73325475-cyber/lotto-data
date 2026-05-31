#!/usr/bin/env python3
"""운영자용: 엑셀 → draws_v{version}.json + manifest.json 변환 스크립트.

사용 예:
  python tools/convert_excel_to_draws.py "로또 회차별 당첨번호.xlsx" --version 2 --output-dir dist/

엑셀 컬럼(동행복권 export 기준):
  B: 회차, C~H: 번호1~6, I: 보너스
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

try:
    import openpyxl
except ImportError:
    raise SystemExit("pip install openpyxl")


def parse_excel(path: Path) -> list[dict]:
    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb.active
    draws = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or row[1] is None:
            continue
        draw_no = int(row[1])
        win6 = sorted(int(row[j]) for j in range(2, 8))
        bonus = int(row[8])
        draws.append({"drawNo": draw_no, "win6": win6, "bonus": bonus})
    draws.sort(key=lambda d: d["drawNo"])
    return draws


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("excel", type=Path)
    parser.add_argument("--version", type=int, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("dist"))
    parser.add_argument("--base-url", default="https://example.com/lotto")
    args = parser.parse_args()

    draws = parse_excel(args.excel)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    draws_name = f"draws_v{args.version}.json"
    draws_path = args.output_dir / draws_name
    raw = json.dumps(draws, ensure_ascii=False, separators=(",", ":"))
    draws_path.write_text(raw, encoding="utf-8")

    sha = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    manifest = {
        "version": args.version,
        "latestDrawNo": draws[-1]["drawNo"],
        "drawsUrl": f"{args.base_url.rstrip('/')}/{draws_name}",
        "sha256": sha,
        "updatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote {draws_path} ({len(draws)} draws)")
    print(f"sha256={sha}")


if __name__ == "__main__":
    main()
