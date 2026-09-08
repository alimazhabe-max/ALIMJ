import os, sqlite3, tempfile, importlib, hashlib
from pathlib import Path


def load_db(tmp):
    os.environ['BOT_TOKEN'] = 'test-token'
    os.environ['DB_PATH'] = str(tmp / 'test.db')
    import bot.config
    importlib.reload(bot.config)
    import bot.database
    importlib.reload(bot.database)
    bot.database.init_db()
    return bot.database


def test_user_preferences_roundtrip(tmp_path):
    db = load_db(tmp_path)
    db.save_user(42, 'Ali')
    assert db.get_user_preferences(42) == {'response_style': 'balanced', 'currency': 'USD'}
    db.set_user_preference(42, 'response_style', 'short')
    db.set_user_preference(42, 'currency', 'EUR')
    assert db.get_user_preferences(42) == {'response_style': 'short', 'currency': 'EUR'}
    try:
        db.set_user_preference(42, 'bad', 'x')
        assert False
    except ValueError:
        pass
    db.clear_user_preferences(42)
    assert db.get_user_preferences(42) == {'response_style': 'balanced', 'currency': 'USD'}


def test_top_features_is_bounded_and_ordered(tmp_path):
    db = load_db(tmp_path)
    db.save_user(7, 'A')
    db.track_usage(7, 'market')
    db.track_usage(7, 'market')
    db.track_usage(7, 'weather')
    assert db.get_top_user_features(7, 1)[0][0] == 'market'
    assert len(db.get_top_user_features(7, 20)) <= 10


def test_jokes_immutable():
    p = Path(__file__).parents[1] / 'bot/features/fun/jokes_data.json'
    assert hashlib.sha256(p.read_bytes()).hexdigest() == 'dc573e2a954af897350caa4183a98f33d5ed71327fed02c7ebe053d893e3a508'
