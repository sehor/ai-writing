from __future__ import annotations

import os
from urllib.parse import urlparse

import httpx
from pydantic import ValidationError

from app.integrations.knowledge_compiler import (
    DisabledKnowledgeCompiler,
    KnowledgeCompiler,
    KnowledgeCompilerRequest,
    KnowledgeCompilerResult,
)

DEFAULT_CLP_BASE_URL = "http://127.0.0.1:43117"
DEFAULT_CLP_TIMEOUT_SECONDS = 8.0
DEFAULT_CLP_COMPILER_VERSION = "llm-wiki-clp"
CLP_EXTRACT_REVISION_PATH = "/v1/extract-revision"
CLP_BASE_URL_ENV = "AI_WRITING_CLP_BASE_URL"
CLP_TIMEOUT_ENV = "AI_WRITING_CLP_TIMEOUT_SECONDS"
CLP_COMPILER_VERSION_ENV = "AI_WRITING_CLP_COMPILER_VERSION"


class KnowledgeCompilerError(RuntimeError):
    pass


class KnowledgeCompilerTransportError(KnowledgeCompilerError):
    pass


class KnowledgeCompilerResponseError(KnowledgeCompilerError):
    pass


class KnowledgeCompilerConfigurationError(KnowledgeCompilerError):
    pass


class UnavailableKnowledgeCompiler:
    """Configured CLP adapter that could not be constructed safely.

    Keep the application and authoritative authoring paths available, but
    fail every CLP extraction so Outbox records the configuration error and
    preserves its normal retry semantics instead of caching an empty success.
    """

    def __init__(self, *, compiler_version: str, error: Exception) -> None:
        self.compiler_version = compiler_version.strip() or DEFAULT_CLP_COMPILER_VERSION
        self._error_message = str(error)

    def extract_revision(self, request: KnowledgeCompilerRequest) -> KnowledgeCompilerResult:
        raise KnowledgeCompilerConfigurationError(self._error_message)


class LlmWikiClpClient:
    """Local HTTP/JSON adapter for the LLM Wiki CLP sidecar.

    The adapter owns no Narrative Domain mutation capability. It accepts an
    application-defined request DTO and validates the complete response into
    application-defined candidate DTOs before returning anything upstream.
    """

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_CLP_BASE_URL,
        timeout_seconds: float = DEFAULT_CLP_TIMEOUT_SECONDS,
        compiler_version: str = DEFAULT_CLP_COMPILER_VERSION,
        http_client: httpx.Client | None = None,
    ) -> None:
        normalized = base_url.rstrip("/")
        _validate_loopback_base_url(normalized)
        if timeout_seconds <= 0:
            raise ValueError("CLP timeout_seconds must be greater than zero.")
        if not compiler_version.strip():
            raise ValueError("CLP compiler_version cannot be blank.")
        self.base_url = normalized
        self.timeout_seconds = timeout_seconds
        self.compiler_version = compiler_version.strip()
        self._http_client = http_client

    def extract_revision(self, request: KnowledgeCompilerRequest) -> KnowledgeCompilerResult:
        if request.compiler_version != self.compiler_version:
            raise ValueError(
                "Compiler request version does not match the configured CLP adapter version."
            )
        client = self._http_client or httpx.Client()
        owns_client = self._http_client is None
        try:
            try:
                response = client.post(
                    f"{self.base_url}{CLP_EXTRACT_REVISION_PATH}",
                    json=request.model_dump(mode="json"),
                    timeout=self.timeout_seconds,
                )
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                raise KnowledgeCompilerTransportError(
                    f"CLP sidecar request failed: {type(exc).__name__}: {exc}"
                ) from exc
            if response.status_code < 200 or response.status_code >= 300:
                raise KnowledgeCompilerTransportError(
                    f"CLP sidecar returned HTTP {response.status_code}."
                )
            try:
                payload = response.json()
            except ValueError as exc:
                raise KnowledgeCompilerResponseError(
                    "CLP sidecar returned malformed JSON."
                ) from exc
            try:
                result = KnowledgeCompilerResult.model_validate(payload)
            except ValidationError as exc:
                raise KnowledgeCompilerResponseError(
                    f"CLP sidecar returned an invalid candidate response: {exc}"
                ) from exc
            _validate_response_identity(request, result)
            return result
        finally:
            if owns_client:
                client.close()


def get_knowledge_compiler() -> KnowledgeCompiler:
    """Resolve the optional local CLP bridge without owning app availability."""
    base_url = os.environ.get(CLP_BASE_URL_ENV, "").strip()
    if not base_url:
        return DisabledKnowledgeCompiler()
    compiler_version = os.environ.get(
        CLP_COMPILER_VERSION_ENV, DEFAULT_CLP_COMPILER_VERSION
    ).strip()
    try:
        timeout_raw = os.environ.get(CLP_TIMEOUT_ENV, str(DEFAULT_CLP_TIMEOUT_SECONDS)).strip()
        try:
            timeout_seconds = float(timeout_raw)
        except ValueError as exc:
            raise ValueError(f"{CLP_TIMEOUT_ENV} must be numeric.") from exc
        return LlmWikiClpClient(
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            compiler_version=compiler_version,
        )
    except Exception as exc:
        return UnavailableKnowledgeCompiler(
            compiler_version=compiler_version,
            error=exc,
        )


def _validate_loopback_base_url(base_url: str) -> None:
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("CLP sidecar URL must use HTTP or HTTPS.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("CLP sidecar URL must not contain credentials, query, or fragment.")
    if parsed.path not in {"", "/"}:
        raise ValueError("CLP sidecar base URL must not contain an application path.")
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("CLP sidecar must use a loopback host.")


def _validate_response_identity(
    request: KnowledgeCompilerRequest,
    result: KnowledgeCompilerResult,
) -> None:
    expected = {
        "project_id": request.project_id,
        "revision_id": request.revision_id,
        "source_ref": request.source_ref,
        "profile_name": request.profile_name,
        "profile_version": request.profile_version,
        "compiler_version": request.compiler_version,
    }
    for field, value in expected.items():
        if getattr(result, field) != value:
            raise KnowledgeCompilerResponseError(
                f"CLP response {field} does not match the request identity."
            )
    for candidate in (
        *result.entity_candidates,
        *result.relation_candidates,
        *result.lifecycle_candidates,
    ):
        if candidate.source_ref != request.source_ref:
            raise KnowledgeCompilerResponseError(
                "CLP candidate source_ref does not match the accepted revision."
            )
        if any(
            not item.excerpt.strip() or item.excerpt not in request.revision_text
            for item in candidate.evidence
        ):
            raise KnowledgeCompilerResponseError(
                "CLP evidence excerpt is not present in the accepted revision."
            )
        if any(item.source_ref != request.source_ref for item in candidate.evidence):
            raise KnowledgeCompilerResponseError(
                "CLP candidate evidence source_ref does not match the accepted revision."
            )
