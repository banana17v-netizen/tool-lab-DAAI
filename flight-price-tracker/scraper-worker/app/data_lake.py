from __future__ import annotations

from datetime import datetime
from pathlib import Path


class DataLakeWriter:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir

    async def write_raw_json(self, ts: datetime, json_line: str) -> Path:
        target_dir = self.base_dir / f"{ts:%Y}" / f"{ts:%m}" / f"{ts:%d}"
        target_dir.mkdir(parents=True, exist_ok=True)

        file_path = target_dir / f"vna_raw_{ts:%Y%m%d}.jsonl"
        with file_path.open("a", encoding="utf-8") as handle:
            handle.write(json_line)
            handle.write("\n")
        return file_path
