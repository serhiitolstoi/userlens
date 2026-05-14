"""Read an events file into a Polars DataFrame. Dispatch by file extension."""

from __future__ import annotations

from pathlib import Path

import polars as pl


class ReadError(ValueError):
    """Raised when the input file cannot be read."""


CSV_SUFFIXES = {".csv", ".tsv"}
PARQUET_SUFFIXES = {".parquet", ".pq"}
JSON_SUFFIXES = {".json"}
JSONL_SUFFIXES = {".jsonl", ".ndjson"}


def read_events(path: Path) -> pl.DataFrame:
    if not path.exists():
        raise ReadError(f"File not found: {path}")
    if path.stat().st_size == 0:
        raise ReadError(f"File is empty: {path}")

    suffix = path.suffix.lower()
    if suffix in CSV_SUFFIXES:
        return _read_csv(path)
    if suffix in PARQUET_SUFFIXES:
        return _read_parquet(path)
    if suffix in JSONL_SUFFIXES:
        return _read_jsonl(path)
    if suffix in JSON_SUFFIXES:
        return _read_json(path)
    raise ReadError(
        f"Unrecognized file extension {suffix!r}. Supported: "
        f"{sorted(CSV_SUFFIXES | PARQUET_SUFFIXES | JSON_SUFFIXES | JSONL_SUFFIXES)}"
    )


def _read_csv(path: Path) -> pl.DataFrame:
    sep = "\t" if path.suffix.lower() == ".tsv" else ","
    return pl.read_csv(path, separator=sep, infer_schema_length=2000)


def _read_parquet(path: Path) -> pl.DataFrame:
    try:
        return pl.read_parquet(path)
    except ImportError as e:
        raise ReadError(
            "Reading Parquet requires pyarrow. Install with `pip install userlens[parquet]`."
        ) from e


def _read_jsonl(path: Path) -> pl.DataFrame:
    return pl.read_ndjson(path)


def _read_json(path: Path) -> pl.DataFrame:
    return pl.read_json(path)


def sample_for_sniff(df: pl.DataFrame, rows: int = 1000) -> pl.DataFrame:
    return df.head(rows)
