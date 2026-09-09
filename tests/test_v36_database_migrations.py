import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JOKES = ROOT / "bot" / "features" / "fun" / "jokes_data.json"
JOKES_SHA256 = "dc573e2a954af897350caa4183a98f33d5ed71327fed02c7ebe053d893e3a508"


class V36DatabaseMigrationTests(unittest.TestCase):
    def test_pre_v36_database_gets_baseline_metadata_without_data_loss(self):
        from bot import database

        old_path = database.DB_PATH
        old_backup = database.BACKUP_DIR
        with tempfile.TemporaryDirectory() as td:
            database.DB_PATH = str(Path(td) / "bot.db")
            database.BACKUP_DIR = Path(td) / "backups"
            try:
                database.init_db()
                database.save_user(36001, "V36", city="Baku", country="Azerbaijan")
                self.assertEqual(database.get_user_city(36001), "Baku")
                self.assertTrue((Path(td) / "bot.pre_migration_v1.db").exists())
                status = database.get_schema_status()
                self.assertEqual(status["version"], 1)
                self.assertEqual(status["supported_version"], 1)
                self.assertEqual(status["migrations"][0]["version"], 1)
                conn = sqlite3.connect(database.DB_PATH)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0], 1)
                self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                conn.close()
            finally:
                database.DB_PATH = old_path
                database.BACKUP_DIR = old_backup

    def test_schema_migration_is_idempotent(self):
        from bot import database

        old_path = database.DB_PATH
        old_backup = database.BACKUP_DIR
        with tempfile.TemporaryDirectory() as td:
            database.DB_PATH = str(Path(td) / "bot.db")
            database.BACKUP_DIR = Path(td) / "backups"
            try:
                database.init_db()
                first = database.get_schema_status()
                database.init_db()
                second = database.get_schema_status()
                self.assertEqual(first["version"], second["version"])
                self.assertEqual(len(first["migrations"]), len(second["migrations"]))
            finally:
                database.DB_PATH = old_path
                database.BACKUP_DIR = old_backup

    def test_future_schema_version_fails_closed(self):
        from bot.database_migrations import ensure_schema_version
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "future.db"
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            conn.execute("INSERT INTO schema_meta(key,value) VALUES('schema_version','999')")
            with self.assertRaises(RuntimeError):
                ensure_schema_version(conn, db)
            conn.close()

    def test_jokes_data_immutable(self):
        self.assertEqual(hashlib.sha256(JOKES.read_bytes()).hexdigest(), JOKES_SHA256)
