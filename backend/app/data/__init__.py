from pathlib import Path
from app.data.interfaces import WritingDataStore
from app.data.sqlite_store import SQLiteWritingDataStore
from app.data.helpers import utc_now

data_store = SQLiteWritingDataStore(Path(__file__).resolve().parent.parent / "data" / "app.db")


def get_data_store() -> WritingDataStore:
    return data_store
