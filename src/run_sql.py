"""Run every analytics query in sql/*.sql and save each result set as a CSV."""
import re
import time
from pathlib import Path

import pandas as pd
import psycopg2

from config import DB_HOST, DB_NAME, DB_PORT, DB_USER, SQL_DIR, SQL_RESULTS_DIR

NAME_HEADER = re.compile(r"^--\s*@name:\s*(\w+)\s*$")


def parse_sql_file(path: Path):
    """Split a query file into (query_name, statement) pairs on ``-- @name:`` headers."""
    queries = []
    name = None
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = NAME_HEADER.match(line)
        if match:
            if name is not None:
                queries.append((name, "\n".join(lines).strip()))
            name = match.group(1)
            lines = []
        elif name is not None:
            lines.append(line)
    if name is not None:
        queries.append((name, "\n".join(lines).strip()))
    return queries


def collect_queries():
    all_queries = []
    for path in sorted(SQL_DIR.glob("*.sql")):
        for name, statement in parse_sql_file(path):
            all_queries.append((path.name, name, statement))
    return all_queries


def run_query(conn, statement: str) -> pd.DataFrame:
    if not statement.lstrip().upper().startswith(("SELECT", "WITH")):
        raise ValueError("only read-only SELECT statements are allowed")
    with conn.cursor() as cur:
        cur.execute(statement)
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]
    return pd.DataFrame(rows, columns=columns)


def main():
    queries = collect_queries()
    SQL_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    conn = psycopg2.connect(dbname=DB_NAME, host=DB_HOST, port=DB_PORT, user=DB_USER)
    conn.autocommit = True
    started = time.perf_counter()
    total_rows = 0
    try:
        for file_name, name, statement in queries:
            try:
                df = run_query(conn, statement)
            except Exception:
                print(f"ERROR in {file_name} :: {name}")
                raise
            out_path = SQL_RESULTS_DIR / f"{name}.csv"
            df.to_csv(out_path, index=False, encoding="utf-8")
            total_rows += len(df)
            print(f"{name}: {len(df):,} rows")
    finally:
        conn.close()
    elapsed = time.perf_counter() - started
    print(f"total queries: {len(queries)} | total rows: {total_rows:,} | total time: {elapsed:.2f}s")


if __name__ == "__main__":
    main()
