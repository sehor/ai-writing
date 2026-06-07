from pathlib import Path
import unittest

from app.data import data_store


class DataStoreConfigurationTests(unittest.TestCase):
    def test_default_database_lives_outside_the_app_package(self) -> None:
        backend_dir = Path(__file__).resolve().parents[1]

        self.assertEqual(data_store.database_path, backend_dir / "data" / "app.db")


if __name__ == "__main__":
    unittest.main()
