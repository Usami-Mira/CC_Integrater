"""
Usage: python scripts/inspect_parquet.py <path/to/file.parquet>
Output: data/processed/_schema_report.json + terminal print
"""
import sys
import json
from pathlib import Path

import pandas as pd


def inspect(path: str) -> dict:
    df = pd.read_parquet(path)
    report: dict = {
        "path": path,
        "n_rows": len(df),
        "columns": [],
        "samples": df.head(3).to_dict(orient="records"),
    }
    for col in df.columns:
        s = df[col]
        dropped = s.dropna()
        try:
            n_unique = int(s.nunique(dropna=True))
        except TypeError:
            n_unique = -1  # unhashable type (e.g. dict/list column)
        info: dict = {
            "name": col,
            "dtype": str(s.dtype),
            "n_null": int(s.isna().sum()),
            "n_unique": n_unique,
            "avg_len": float(dropped.astype(str).str.len().mean()) if len(dropped) else 0,
            "max_len": int(dropped.astype(str).str.len().max()) if len(dropped) else 0,
            "sample_values": [str(v)[:200] for v in dropped.head(2).tolist()],
        }
        if info["dtype"] == "object" and len(dropped):
            v = dropped.iloc[0]
            if isinstance(v, (dict, list)):
                info["nested"] = "native"
            elif isinstance(v, str) and v.strip().startswith(("{", "[")):
                try:
                    json.loads(v)
                    info["nested"] = "json_string"
                except Exception:
                    pass
        report["columns"].append(info)

    Path("data/processed").mkdir(parents=True, exist_ok=True)
    out = Path("data/processed/_schema_report.json")
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str)[:6000])
    return report


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/inspect_parquet.py <path/to/file.parquet>")
        sys.exit(1)
    inspect(sys.argv[1])
