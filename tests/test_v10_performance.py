import asyncio
import os
os.environ.setdefault("BOT_TOKEN", "v10-test-token")
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

from bot import database
from bot.utils import observability
from bot.utils import task_manager


class V10PerformanceTests(unittest.TestCase):
    def test_db_concurrent_writes(self):
        with tempfile.TemporaryDirectory() as td:
            old = database.DB_PATH
            database.DB_PATH = str(Path(td) / 'load.db')
            try:
                conn = database.get_db_connection()
                conn.execute('CREATE TABLE load_test (id INTEGER PRIMARY KEY, value TEXT)')
                conn.commit(); conn.close()
                errors = []
                def write(i):
                    try:
                        database._execute_write('INSERT INTO load_test(id,value) VALUES (?,?)', (i, str(i)))
                    except Exception as exc:
                        errors.append(exc)
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
                    list(pool.map(write, range(200)))
                conn = sqlite3.connect(database.DB_PATH)
                count = conn.execute('SELECT COUNT(*) FROM load_test').fetchone()[0]
                conn.close()
                self.assertEqual(errors, [])
                self.assertEqual(count, 200)
            finally:
                database.DB_PATH = old

    def test_observability_is_bounded(self):
        observability.reset()
        for i in range(1000):
            observability.record('test', 'bench', ok=(i % 10 != 0), latency=0.001)
        snap = observability.snapshot()
        self.assertEqual(snap['counters']['test:bench:total'], 1000)
        self.assertEqual(snap['latency']['test:bench']['count'], 200)

    def test_task_manager_cleans_completed_tasks(self):
        async def run():
            task_manager.spawn(asyncio.sleep(0), name='v10-smoke')
            await asyncio.sleep(0.01)
            self.assertEqual(task_manager.stats()['active'], 0)
            await task_manager.shutdown()
        asyncio.run(run())


if __name__ == '__main__':
    unittest.main()
