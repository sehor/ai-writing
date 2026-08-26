"""Project backup / restore HTTP surface (P2-07).

- ``GET  /projects/{id}/backup``          — download the ZIP package.
- ``POST /projects/backups/preview``      — upload a package, see what an import would do.
- ``POST /projects/backups/import``       — restore; ``overwrite=true`` replaces an existing project.

Uploads use raw request bodies (``application/zip`` / ``application/octet-stream``)
so no multipart dependency is required.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response

from app.config import resolve_data_root
from app.data import SQLiteWritingDataStore, get_data_store
from app.services.backup_service import (
    BackupConflictError,
    BackupError,
    BackupNotFoundError,
    BackupVersionError,
    ProjectBackupService,
)

router = APIRouter(tags=["backups"])


def get_backup_service(
    data_store: SQLiteWritingDataStore = Depends(get_data_store),
) -> ProjectBackupService:
    return ProjectBackupService(
        data_store,
        resolve_data_root() / "projects",
    )


def _map_backup_errors(exc: BackupError) -> HTTPException:
    if isinstance(exc, BackupNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, BackupConflictError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, BackupVersionError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/projects/{project_id}/backup")
def export_project_backup(
    project_id: str,
    service: ProjectBackupService = Depends(get_backup_service),
) -> Response:
    try:
        package = service.export_package(project_id)
    except BackupError as exc:
        raise _map_backup_errors(exc) from exc
    filename = f"project-{project_id}-backup.zip"
    return Response(
        content=package,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/projects/backups/preview")
async def preview_project_backup(
    request: Request,
    service: ProjectBackupService = Depends(get_backup_service),
) -> dict:
    package = await request.body()
    try:
        return service.preview_import(package)
    except BackupError as exc:
        raise _map_backup_errors(exc) from exc


@router.post("/projects/backups/import")
async def import_project_backup(
    request: Request,
    overwrite: bool = False,
    service: ProjectBackupService = Depends(get_backup_service),
) -> dict:
    package = await request.body()
    try:
        return service.import_package(package, overwrite=overwrite)
    except BackupError as exc:
        raise _map_backup_errors(exc) from exc
