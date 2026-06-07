import unittest

from fastapi import HTTPException

from app.dependencies import require_project


class MissingProjectStore:
    def project_exists(self, project_id: str) -> bool:
        return False


class ExistingProjectStore:
    def project_exists(self, project_id: str) -> bool:
        return True


class ProjectDependencyTests(unittest.TestCase):
    def test_require_project_rejects_missing_project(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            require_project("missing", MissingProjectStore())

        self.assertEqual(raised.exception.status_code, 404)
        self.assertEqual(raised.exception.detail, "Project not found.")

    def test_require_project_accepts_existing_project(self) -> None:
        require_project("existing", ExistingProjectStore())


if __name__ == "__main__":
    unittest.main()
