import logging
from logging.handlers import RotatingFileHandler
import sys

def setup_logger(name="bot", level="INFO"):
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))

    # قالب لاگ
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # خروجی کنسول
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # خروجی فایل با چرخش
    file_handler = RotatingFileHandler('bot.log', maxBytes=5*1024*1024, backupCount=5)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger

logger = setup_logger(level="INFO")
