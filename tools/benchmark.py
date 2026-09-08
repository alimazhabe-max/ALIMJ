"""Small, dependency-free performance smoke benchmark for ALIMJ.
Run: python tools/benchmark.py [writes] [workers]
This uses a temporary SQLite database and never touches production data.
"""
from __future__ import annotations
import concurrent.futures
import sqlite3
import sys
import tempfile
import time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))
from bot import database


def main() -> None:
    writes = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 16
    with tempfile.TemporaryDirectory(prefix='alimj-v10-') as td:
        old = database.DB_PATH
        database.DB_PATH = str(Path(td) / 'bench.db')
        try:
            conn = database.get_db_connection()
            conn.execute('CREATE TABLE bench (id INTEGER PRIMARY KEY, value TEXT)')
            conn.commit(); conn.close()
            start = time.perf_counter()
            errors = []
            def write(i: int):
                try:
                    database._execute_write('INSERT INTO bench(id,value) VALUES (?,?)', (i, str(i)))
                except Exception as exc:
                    errors.append(exc)
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
                list(pool.map(write, range(writes)))
            elapsed = time.perf_counter() - start
            conn = sqlite3.connect(database.DB_PATH)
            count = conn.execute('SELECT COUNT(*) FROM bench').fetchone()[0]
            conn.close()
            print(f'writes={writes} workers={workers} elapsed={elapsed:.3f}s throughput={count/elapsed:.1f}/s errors={len(errors)}')
            if errors:
                raise SystemExit(1)
        finally:
            database.DB_PATH = old

if __name__ == '__main__':
    main()
