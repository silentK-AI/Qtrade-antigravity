import os, sys
BASE_DIR = os.path.abspath('.')
from dotenv import load_dotenv
load_dotenv(os.path.join(BASE_DIR, ".env"))
print("After load_dotenv:", os.getenv("SERVERCHAN_KEY"))
from monitor.notifier import Notifier
n = Notifier()
print("Notifier key:", n._serverchan_key)
