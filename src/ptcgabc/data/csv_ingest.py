"""RAW CSV intake — exact schema discovery, encoding detection, lossless row retention.

Blueprint §3/PROBLEM 3:
    RAW CSV → EXACT SCHEMA DISCOVERY → ROW-LEVEL PRESERVATION
            → GROUP BY VERIFIED CARD ID → AGGREGATE → CANONICAL CARD OBJECT

The raw file is never flattened prematurely.
"""

from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import schema_registry
from ..errors import FailureCategory
from ..reproduce import sha256_file


class DataParseError(Exception):
    category = FailureCategory.DATA_PARSE_ERROR

    def __init__(self, message: str, path: str = ""):
        super().__init__(message)
        self.message = message
        self.path = path


def detect_encoding(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    try:
        raw.decode("utf-8")
        enc = "utf-8-sig" if has_bom else "utf-8"
        return {"encoding": enc, "decodable": True, "checked": True, "bom": has_bom}
    except UnicodeDecodeError:
        pass
    try:
        raw.decode("latin-1")
        return {"encoding": "latin-1", "decodable": True, "checked": True, "fallback": True, "bom": False}
    except UnicodeDecodeError:  # pragma: no cover - latin-1 never fails
        return {"encoding": "latin-1", "decodable": True, "checked": True, "fallback": True, "bom": False}


def _read_text(path: Path) -> str:
    info = detect_encoding(path)
    raw = path.read_bytes()
    if "utf-8" in info["encoding"]:
        return raw.decode("utf-8-sig" if "sig" in info["encoding"] else "utf-8")
    return raw.decode("latin-1")


@dataclass
class RawRow:
    """One physical CSV data row with complete lineage."""

    source_file: str
    row_index: int                 # 1-based row in the physical file (data rows)
    values: dict[str, str]         # normalized header -> raw cell
    raw_values: list[str]
    source_hash: str

    def to_dict(self) -> dict:
        return {
            "source_file": self.source_file,
            "row_index": self.row_index,
            "values": dict(self.values),
            "source_hash": self.source_hash,
        }


@dataclass
class ColumnDiscovery:
    raw_name: str
    normalized: str
    position: int
    null_like_count: int
    distinct_values: list[str]
    status: str

    def to_dict(self) -> dict:
        return {
            "raw_name": self.raw_name,
            "normalized": self.normalized,
            "position": self.position,
            "null_like_count": self.null_like_count,
            "distinct_values": self.distinct_values[:12],
            "status": self.status,
        }


@dataclass
class IngestedFile:
    path: Path
    encoding: str
    sha256: str
    n_rows: int
    n_cols: int
    columns: list[str]             # normalized header names
    discovery: list[ColumnDiscovery]
    rows: list[RawRow]
    warnings: list[str] = field(default_factory=list)

    def validate(self) -> "IngestedFile":
        if not self.rows:
            raise DataParseError("no data rows", str(self.path))
        expected = len(self.columns)
        for r in self.rows:
            if len(r.raw_values) != expected:
                raise DataParseError(
                    f"row {r.row_index} has {len(r.raw_values)} cells, header has {expected}",
                    str(self.path),
                )
            missing = [c for c in self.columns if c not in r.values]
            if missing:
                raise DataParseError(
                    f"row {r.row_index} missing values for {missing}",
                    str(self.path),
                )
        return self

    def to_dict(self) -> dict:
        return {
            "path": str(self.path),
            "encoding": self.encoding,
            "sha256": self.sha256,
            "n_rows": self.n_rows,
            "n_cols": self.n_cols,
            "columns": list(self.columns),
            "discovery": [d.to_dict() for d in self.discovery],
            "warnings": list(self.warnings),
        }


def _null_like(v: str) -> bool:
    v = v.strip()
    return v in ("", "n/a", "N/A", "null", "None")


def ingest_csv(path: Path, *, primary: bool = True) -> IngestedFile:
    if not path.exists():
        raise DataParseError(f"file does not exist: {path}", str(path))
    enc = detect_encoding(path)["encoding"]
    text = _read_text(path)

    try:
        reader = csv.reader(text.splitlines(True))
        table = list(reader)
    except Exception as e:  # pragma: no cover - csv errors
        raise DataParseError(f"csv parse failed: {e}", str(path))

    if not table:
        raise DataParseError("empty csv", str(path))

    raw_header = [c.strip() for c in table[0]]
    normalized_cols = [schema_registry.normalize_header(h) for h in raw_header]

    unknown = schema_registry.critical_unknown(normalized_cols)
    if unknown:
        raise DataParseError(
            f"unmapped columns blocked ingestion: {unknown}",
            str(path),
        )

    n_cols = len(normalized_cols)
    source_hash = sha256_file(path)
    rows: list[RawRow] = []
    warnings: list[str] = []

    for i, cells in enumerate(table[1:], start=2):
        if len(cells) == 1 and cells[0].strip() == "":
            warnings.append(f"skipping blank physical line at file line {i}")
            continue
        if len(cells) != n_cols:
            raise DataParseError(
                f"row {i} has {len(cells)} cells; header has {n_cols}; line={cells[:3]!r}",
                str(path),
            )
        values = {
            normalized_cols[j]: (cells[j].strip() if cells[j] is not None else "")
            for j in range(n_cols)
        }
        rows.append(
            RawRow(
                source_file=str(path),
                row_index=i,
                values=values,
                raw_values=list(cells),
                source_hash=source_hash,
            )
        )

    discovery: list[ColumnDiscovery] = []
    for pos, col in enumerate(normalized_cols):
        vals = [r.values[col] for r in rows]
        null_like = sum(1 for v in vals if _null_like(v))
        distinct = sorted({v for v in vals if not _null_like(v)})
        mapping = schema_registry.mapping_for(col)
        discovery.append(
            ColumnDiscovery(
                raw_name=raw_header[pos],
                normalized=col,
                position=pos,
                null_like_count=null_like,
                distinct_values=distinct,
                status=mapping.status.value,
            )
        )

    return IngestedFile(
        path=path,
        encoding=enc,
        sha256=source_hash,
        n_rows=len(rows),
        n_cols=n_cols,
        columns=normalized_cols,
        discovery=discovery,
        rows=rows,
        warnings=warnings,
    )


def rows_per_card(ing: IngestedFile) -> dict[str, int]:
    return Counter(r.values["Card ID"] for r in ing.rows)


def card_id_validation(ing: IngestedFile) -> dict[str, Any]:
    """Validate Card ID column: no blanks, no dup normalization issues, int-like."""
    ids = [r.values["Card ID"] for r in ing.rows]
    blank = [i for i, v in enumerate(ids) if not v]
    non_int = [v for v in sorted(set(ids)) if not v.isdigit()]
    dup_non_int = [v for v, c in Counter(ids).items() if c > 1 and not v.isdigit()]
    # distinct names per id (multiple printings share id -> many names)
    return {
        "n_rows": len(ids),
        "blank_ids": len(blank),
        "non_int_ids": non_int[:10],
        "duplicate_non_int_ids": dup_non_int,
        "distinct_ids": len(set(ids)),
        "ok": not blank and not non_int,
    }