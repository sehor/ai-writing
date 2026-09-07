"""HTTP translation for application failures; services retain structured evidence."""

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.errors import (
    ApplicationError,
    InvalidOperationError,
    ProviderConfigurationError,
    ProviderExecutionError,
    ResourceNotFoundError,
    StateConflictError,
)

ERROR_STATUS = {
    ResourceNotFoundError: status.HTTP_404_NOT_FOUND,
    StateConflictError: status.HTTP_409_CONFLICT,
    InvalidOperationError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    ProviderConfigurationError: status.HTTP_501_NOT_IMPLEMENTED,
    ProviderExecutionError: status.HTTP_502_BAD_GATEWAY,
}


def application_http_exception(
    exc: ApplicationError, headers: dict[str, str] | None = None
) -> HTTPException:
    # Preserve the registered status for more specific application subclasses too.
    code = next(ERROR_STATUS[base] for base in type(exc).__mro__ if base in ERROR_STATUS)
    return HTTPException(status_code=code, detail=exc.detail, headers=headers)


async def application_error_response(request: Request, exc: ApplicationError) -> JSONResponse:
    translated = application_http_exception(exc)
    return JSONResponse(status_code=translated.status_code, content={"detail": translated.detail})


def install_application_error_handlers(app: FastAPI) -> None:
    for error_type in ERROR_STATUS:
        app.add_exception_handler(error_type, application_error_response)
