from pathlib import Path

from app.data.mixins.projects import ProjectsDataMixin
from app.data.mixins.artifacts import ArtifactsDataMixin
from app.data.mixins.canon import CanonDataMixin
from app.data.mixins.scenes import ScenesDataMixin
from app.data.mixins.manuscript import ManuscriptDataMixin
from app.data.mixins.memory import MemoryDataMixin
from app.data.mixins.wiki import WikiDataMixin
from app.data.mixins.outbox import OutboxDataMixin


class SQLiteWritingDataStore(
    ProjectsDataMixin,
    ArtifactsDataMixin,
    CanonDataMixin,
    ScenesDataMixin,
    ManuscriptDataMixin,
    MemoryDataMixin,
    WikiDataMixin,
    OutboxDataMixin,
):
    def __init__(self, database_path: Path):
        self.database_path = database_path
