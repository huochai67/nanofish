"""Build EH tag translation SQLite DB from EhTagTranslation JSON."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

SQL_DIR = Path(__file__).resolve().parent
DEFAULT_JSON = SQL_DIR / "db.text.json"
DEFAULT_DB = SQL_DIR / "o.db"

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS tags_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    namespace TEXT NOT NULL,
    tag TEXT NOT NULL,
    tran TEXT NOT NULL,
    UNIQUE(namespace, tag)
);
"""

INSERT_SQL = (
    "INSERT OR IGNORE INTO tags_data (namespace, tag, tran) VALUES (?, ?, ?)"
)


def process_json_to_sqlite(json_path: str | Path, db_path: str | Path) -> tuple[int, int]:
    """
    Read tag JSON and write/overwrite a SQLite database.

    Returns:
        (inserted_count, skipped_count)
    """
    json_path = Path(json_path)
    db_path = Path(db_path)

    if not json_path.is_file():
        raise FileNotFoundError(f"JSON file not found: {json_path}")

    with json_path.open(encoding="utf-8") as f:
        data = json.load(f)

    if "data" not in data or not isinstance(data["data"], list):
        raise ValueError("JSON missing top-level 'data' array")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(CREATE_TABLE_SQL)

        insert_count = 0
        skipped_count = 0

        for item in data["data"]:
            try:
                namespace = item["namespace"]
                if "data" not in item or not isinstance(item["data"], dict):
                    print(
                        f"warning: namespace '{namespace}' missing data dict, skipped",
                        file=sys.stderr,
                    )
                    continue

                for key, value in item["data"].items():
                    tag = key
                    tran = value["name"]
                    cursor.execute(INSERT_SQL, (namespace, tag, tran))
                    if cursor.rowcount > 0:
                        insert_count += 1
                    else:
                        skipped_count += 1
            except KeyError as e:
                print(f"warning: missing key {e}, record skipped", file=sys.stderr)
            except TypeError:
                print("warning: unexpected record shape, skipped", file=sys.stderr)

        conn.commit()
    finally:
        conn.close()

    return insert_count, skipped_count


def ensure_tag_db(
    db_path: str | Path,
    json_path: str | Path | None = None,
    *,
    force: bool = False,
) -> Path:
    """
    Ensure the tag SQLite DB exists; build from JSON if missing (or force=True).
    """
    db_path = Path(db_path)
    json_path = Path(json_path) if json_path is not None else DEFAULT_JSON

    if db_path.is_file() and not force:
        return db_path

    inserted, skipped = process_json_to_sqlite(json_path, db_path)
    print(
        f"built EH tag DB: {db_path} "
        f"(inserted={inserted}, skipped={skipped}, source={json_path})"
    )
    return db_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build EH tag translation SQLite DB")
    parser.add_argument(
        "-j",
        "--json",
        type=Path,
        default=DEFAULT_JSON,
        help=f"source JSON (default: {DEFAULT_JSON})",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_DB,
        help=f"output SQLite path (default: {DEFAULT_DB})",
    )
    parser.add_argument(
        "--skip-if-exists",
        action="store_true",
        help="do nothing if the output DB already exists",
    )
    args = parser.parse_args(argv)

    try:
        ensure_tag_db(args.output, args.json, force=not args.skip_if_exists)
    except (OSError, ValueError, json.JSONDecodeError, sqlite3.Error) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
