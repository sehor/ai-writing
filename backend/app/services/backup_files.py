"""Stage module files and retain the old directory until SQLite commits."""

import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path

from app.services.backup_format import BackupError


def checked_modules_dir(projects_root: Path, project_id: str) -> Path:
    root = projects_root.resolve()
    target = root / project_id / "modules"
    for path in (target.parent, target):
        if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
            raise BackupError("Project module directories must not be links.")
        if path.exists() and not path.is_dir():
            raise BackupError("Project module path is not a directory.")
    if not target.resolve().is_relative_to(root):
        raise BackupError("Project module directory escapes the project root.")
    return target


@contextmanager
def staged_modules(projects_root: Path, project_id: str, files: list[tuple[str, bytes]]):
    target = checked_modules_dir(projects_root, project_id)
    projects_root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".restore-", dir=projects_root))
    prepared, previous = staging / "new", staging / "old"
    prepared.mkdir()
    swapped = False
    cleanable = True
    created_parent = not target.parent.exists()

    def install():
        nonlocal swapped
        checked_modules_dir(projects_root, project_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            target.rename(previous)
        prepared.rename(target)
        swapped = True

    try:
        for name, content in files:
            path = prepared / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        yield install
    except BaseException:
        try:
            if swapped:
                target.rename(staging / "failed")
            if previous.exists():
                previous.rename(target)
            if created_parent and target.parent.exists():
                target.parent.rmdir()
        except OSError as exc:
            cleanable = False
            raise BackupError(
                f"Module rollback needs manual recovery; original files retained at {previous}."
            ) from exc
        raise
    finally:
        if cleanable:
            # Cleanup failure after commit retains a copy, not a false failure.
            shutil.rmtree(staging, ignore_errors=True)
