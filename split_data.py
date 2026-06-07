import os
from pathlib import Path

backend_dir = Path('e:/projects/ai-writing/backend/app')
data_py = backend_dir / 'data.py'
lines = data_py.read_text(encoding='utf-8').splitlines()

def get_lines(start, end):
    return '\n'.join(lines[start-1:end])

data_dir = backend_dir / 'data'
data_dir.mkdir(parents=True, exist_ok=True)
mixins_dir = data_dir / 'mixins'
mixins_dir.mkdir(parents=True, exist_ok=True)

imports = get_lines(1, 38)
protocol = get_lines(40, 219)

# Interfaces
(data_dir / 'interfaces.py').write_text(f"{imports}\n\n{protocol}\n", encoding='utf-8')

# Helpers
helpers_content = f"""{imports}

{get_lines(1567, 1586)}

{get_lines(1589, 1596)}

{get_lines(1911, 1912)}
"""
(data_dir / 'helpers.py').write_text(helpers_content, encoding='utf-8')

# Mixins
domains = {
    'projects': {
        'methods': [(226, 400), (403, 412), (414, 423), (425, 448), (450, 460), (462, 468), (470, 487)],
        'helpers': [(1563, 1564), (1599, 1605)]
    },
    'artifacts': {
        'methods': [(489, 500), (502, 514), (516, 533)],
        'helpers': [(1608, 1614)]
    },
    'canon': {
        'methods': [(535, 547), (549, 575), (577, 610), (612, 618)],
        'helpers': [(1617, 1628), (1631, 1642)]
    },
    'scenes': {
        'methods': [(620, 633), (635, 649), (651, 678), (680, 721), (723, 729)],
        'helpers': [(1645, 1660), (1663, 1680)]
    },
    'manuscript': {
        'methods': [
            (731, 742), (744, 769), (771, 796), (798, 813),
            (896, 908), (910, 940), (942, 970), (972, 985),
            (987, 999), (1001, 1013), (1015, 1028),
            (1030, 1131), (1133, 1146), (1148, 1240), (1242, 1326)
        ],
        'helpers': [
            (1683, 1690), (1693, 1702),
            (1733, 1746), (1749, 1764),
            (1767, 1777), (1780, 1792),
            (1795, 1805), (1808, 1820)
        ]
    },
    'memory': {
        'methods': [(815, 826), (828, 853), (855, 886), (888, 894)],
        'helpers': [(1705, 1715), (1718, 1730)]
    },
    'wiki': {
        'methods': [
            (1328, 1340), (1342, 1373), (1375, 1406), (1408, 1442), (1444, 1457),
            (1459, 1474), (1476, 1509), (1511, 1542), (1544, 1560)
        ],
        'helpers': [
            (1823, 1837), (1840, 1856),
            (1859, 1884), (1887, 1908)
        ]
    }
}

for domain, details in domains.items():
    methods_str = "\n".join(get_lines(start, end) for start, end in details['methods'])
    helpers_str = "\n".join(get_lines(start, end) for start, end in details['helpers'])
    class_name = domain.capitalize() + "DataMixin"
    
    file_content = f"{imports}\nfrom app.data.helpers import ensure_column, make_record_id, utc_now\n\n{helpers_str}\n\nclass {class_name}:\n{methods_str}\n"
    (mixins_dir / f'{domain}.py').write_text(file_content, encoding='utf-8')

# sqlite_store.py
sqlite_store_content = f"""{imports}
from app.data.mixins.projects import ProjectsDataMixin
from app.data.mixins.artifacts import ArtifactsDataMixin
from app.data.mixins.canon import CanonDataMixin
from app.data.mixins.scenes import ScenesDataMixin
from app.data.mixins.manuscript import ManuscriptDataMixin
from app.data.mixins.memory import MemoryDataMixin
from app.data.mixins.wiki import WikiDataMixin
from app.data.interfaces import WritingDataStore

class SQLiteWritingDataStore(
    ProjectsDataMixin,
    ArtifactsDataMixin,
    CanonDataMixin,
    ScenesDataMixin,
    ManuscriptDataMixin,
    MemoryDataMixin,
    WikiDataMixin,
):
{get_lines(223, 224)}
"""
(data_dir / 'sqlite_store.py').write_text(sqlite_store_content, encoding='utf-8')

# __init__.py
init_content = f"""from pathlib import Path
from app.data.interfaces import WritingDataStore
from app.data.sqlite_store import SQLiteWritingDataStore
from app.data.helpers import utc_now

{get_lines(1915, 1919)}
"""
(data_dir / '__init__.py').write_text(init_content, encoding='utf-8')

import shutil
shutil.move(data_py, data_py.with_suffix('.py.bak'))
print("Successfully split data.py into modules.")
