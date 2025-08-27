
from datetime import datetime

def now() -> datetime:
    return datetime.now(datetime.timezone.utc)