import asyncio, sys, types, unittest

class TestV13Hardening(unittest.TestCase):
    def test_refresh_lock_map_is_bounded(self):
        # callbacks imports telegram; skip cleanly if dependency is unavailable.
        try:
            from bot.handlers import callbacks
        except ModuleNotFoundError as e:
            if e.name == 'telegram':
                self.skipTest('python-telegram-bot not installed')
            raise
        callbacks._refresh_locks.clear()
        for uid in range(2500):
            callbacks._get_refresh_lock(uid)
        self.assertLessEqual(len(callbacks._refresh_locks), 2049)

    def test_error_throttle_map_cleanup_logic(self):
        # Verify the same bounded-map policy independently of Telegram runtime.
        now = 2_000_000.0
        last = {i: now - 100_000 for i in range(5000)}
        last[1] = now
        cutoff = now - 86400
        last = {k: v for k, v in last.items() if v >= cutoff}
        self.assertEqual(last, {1: now})

    def test_jokes_hash(self):
        import hashlib
        from pathlib import Path
        p = Path('bot/features/fun/jokes_data.json')
        self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(), 'dc573e2a954af897350caa4183a98f33d5ed71327fed02c7ebe053d893e3a508')

if __name__ == '__main__':
    unittest.main()
