from app.config import resolve_data_root
from app.data.interfaces import WritingDataStore
from app.data.sqlite_store import SQLiteWritingDataStore
from app.data.helpers import utc_now

data_store = SQLiteWritingDataStore(resolve_data_root() / "app.db")


def get_data_store() -> WritingDataStore:
    return data_store
