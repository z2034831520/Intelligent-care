from __future__ import annotations

import json

from .manual_patrol import run_manual_patrol


def main() -> None:  # pragma: no cover
    record = run_manual_patrol()
    print(json.dumps(record.to_dict(), ensure_ascii=False, indent=2))
