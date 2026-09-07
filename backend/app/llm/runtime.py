"""Resilient model execution with repair, failover, and safe run persistence."""

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import uuid4

from app.llm.capabilities import (
    ModelCapabilities,
    ModelCatalog,
    ModelProfile,
    default_model_catalog,
)
from app.llm.gateway import (
    ModelCompletion,
    ModelGateway,
    ModelGatewayError,
    ModelRequest,
    ModelResult,
)
from app.llm.registry import ModelGatewayRegistry, default_model_gateway_registry
from app.models import (
    GenerationAttemptCreate,
    GenerationRun,
    GenerationRunCreate,
    GenerationRunUpdate,
    ModelExecutionOptions,
)
from app.observability import log_event
from app.prompts import compile_repair_prompt


ContentValidator = Callable[[str], Any]
FALLBACK_ERROR_CODES = {
    "not_configured",
    "configuration",
    "sdk_unavailable",
    "rate_limit",
    "timeout",
    "unavailable",
    "context_overflow",
    "output_truncated",
    "empty_response",
    "invalid_response",
    "execution",
}


class GenerationRunRecorder(Protocol):
    def create_generation_run(self, create: GenerationRunCreate) -> GenerationRun: ...

    def add_generation_attempt(self, run_id: str, create: GenerationAttemptCreate) -> object: ...

    def finish_generation_run(self, run_id: str, update: GenerationRunUpdate) -> None: ...


@dataclass(frozen=True, slots=True)
class ModelExecution:
    completion: ModelCompletion
    generation_run_id: str = ""
    attempt_count: int = 1
    repair_count: int = 0
    fallback_count: int = 0
    validated_value: Any = None


class ModelRuntime:
    def __init__(
        self,
        registry: ModelGatewayRegistry | None = None,
        catalog: ModelCatalog | None = None,
        recorder: GenerationRunRecorder | None = None,
    ) -> None:
        self.registry = registry or default_model_gateway_registry
        self.catalog = catalog or default_model_catalog
        self.recorder = recorder

    def has_configured_gateway(self) -> bool:
        for profile in self.catalog.profiles():
            try:
                self.registry.create(profile.provider_id, profile.model_id or None)
                return True
            except ModelGatewayError as exc:
                if not exc.is_configuration_error:
                    return True
        return False

    def execute(
        self,
        request: ModelRequest,
        options: ModelExecutionOptions | None = None,
        *,
        validate_content: ContentValidator | None = None,
    ) -> ModelExecution:
        active_options = options or ModelExecutionOptions()
        validator = validate_content or _default_validator(request)
        candidates = self._candidates(active_options)
        run_id = self._start_run(request, active_options)
        started = time.perf_counter()
        attempt_index = 0
        repair_count = 0
        fallback_count = 0
        input_tokens = 0
        output_tokens = 0
        last_error = ModelGatewayError(
            "not_configured",
            "No compatible model gateway is configured.",
        )

        for candidate_index, profile in enumerate(candidates):
            attempt_kind = "primary" if candidate_index == 0 else "fallback"
            if candidate_index > 0:
                fallback_count += 1
            if not profile.capabilities.supports(request):
                attempt_index += 1
                last_error = ModelGatewayError(
                    "configuration",
                    "Selected model does not satisfy the generation policy.",
                    provider_id=profile.provider_id,
                )
                self._record_error_attempt(
                    run_id,
                    attempt_index,
                    attempt_kind,
                    profile,
                    last_error,
                    0,
                )
                continue

            try:
                gateway = self.registry.create(profile.provider_id, profile.model_id or None)
            except ModelGatewayError as exc:
                attempt_index += 1
                last_error = exc
                self._record_error_attempt(
                    run_id,
                    attempt_index,
                    attempt_kind,
                    profile,
                    exc,
                    0,
                )
                if not active_options.allow_fallback or exc.code not in FALLBACK_ERROR_CODES:
                    break
                continue

            attempt_index += 1
            result, validated, error, elapsed = self._attempt(
                gateway,
                request,
                validator,
            )
            input_tokens += (result.usage.input_tokens or 0) if result else 0
            output_tokens += (result.usage.output_tokens or 0) if result else 0
            if error is None and result is not None:
                self._record_success_attempt(
                    run_id,
                    attempt_index,
                    attempt_kind,
                    profile,
                    result,
                    elapsed,
                )
                return self._success(
                    request,
                    result,
                    validated,
                    profile,
                    run_id,
                    attempt_index,
                    repair_count,
                    fallback_count,
                    input_tokens,
                    output_tokens,
                    started,
                )

            last_error = error or last_error
            self._record_error_attempt(
                run_id,
                attempt_index,
                attempt_kind,
                profile,
                last_error,
                elapsed,
                result,
            )
            if (
                result is not None
                and last_error.code == "invalid_response"
                and active_options.allow_repair
            ):
                repair_count += 1
                attempt_index += 1
                repair_request = ModelRequest(
                    prompt=compile_repair_prompt(
                        request.prompt,
                        result.content,
                        last_error.safe_message,
                    ),
                    policy=request.policy,
                    metadata={**request.metadata, "repair_for": request.prompt.prompt_id},
                )
                repaired, repaired_value, repair_error, repair_elapsed = self._attempt(
                    gateway,
                    repair_request,
                    validator,
                )
                input_tokens += (repaired.usage.input_tokens or 0) if repaired else 0
                output_tokens += (repaired.usage.output_tokens or 0) if repaired else 0
                if repair_error is None and repaired is not None:
                    self._record_success_attempt(
                        run_id,
                        attempt_index,
                        "repair",
                        profile,
                        repaired,
                        repair_elapsed,
                    )
                    return self._success(
                        request,
                        repaired,
                        repaired_value,
                        profile,
                        run_id,
                        attempt_index,
                        repair_count,
                        fallback_count,
                        input_tokens,
                        output_tokens,
                        started,
                    )
                last_error = repair_error or last_error
                self._record_error_attempt(
                    run_id,
                    attempt_index,
                    "repair",
                    profile,
                    last_error,
                    repair_elapsed,
                    repaired,
                )

            if not active_options.allow_fallback or last_error.code not in FALLBACK_ERROR_CODES:
                break

        self._finish_run(
            run_id,
            GenerationRunUpdate(
                status="failed",
                error_code=last_error.code,
                safe_error=last_error.safe_message,
                attempt_count=attempt_index,
                repair_count=repair_count,
                fallback_count=fallback_count,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                duration_ms=_elapsed_ms(started),
                completed_at=_utc_now(),
            ),
        )
        log_event(
            "model_generation_run",
            operation=request.prompt.use_case,
            project_id=str(request.metadata.get("project_id", "")),
            run_id=run_id,
            result="failed",
            error_code=last_error.code,
            attempt_count=attempt_index,
            repair_count=repair_count,
            fallback_count=fallback_count,
            duration_ms=_elapsed_ms(started),
        )
        raise last_error

    def _candidates(self, options: ModelExecutionOptions) -> tuple[ModelProfile, ...]:
        try:
            return self.catalog.candidates(
                options.model_profile,
                allow_fallback=options.allow_fallback,
            )
        except LookupError as exc:
            raise ModelGatewayError(
                "configuration",
                "Selected model profile is not available.",
            ) from exc

    def _attempt(
        self,
        gateway: ModelGateway,
        request: ModelRequest,
        validator: ContentValidator | None,
    ) -> tuple[ModelResult | None, Any, ModelGatewayError | None, float]:
        started = time.perf_counter()
        try:
            result = gateway.complete(request)
        except ModelGatewayError as exc:
            return None, None, exc, _elapsed_ms(started)
        except Exception:
            error = ModelGatewayError(
                "execution",
                "Model provider request failed.",
                provider_id=gateway.provider_id,
            )
            return None, None, error, _elapsed_ms(started)
        if validator is None:
            return result, None, None, _elapsed_ms(started)
        try:
            validated = validator(result.content)
        except Exception:
            return (
                result,
                None,
                ModelGatewayError(
                    "invalid_response",
                    "Model response failed local validation.",
                    provider_id=result.provider_id,
                ),
                _elapsed_ms(started),
            )
        return result, validated, None, _elapsed_ms(started)

    def _start_run(self, request: ModelRequest, options: ModelExecutionOptions) -> str:
        if self.recorder is None:
            return ""
        project_id = str(request.metadata.get("project_id", ""))
        if not project_id:
            raise RuntimeError("Persisted model execution requires project_id metadata.")
        run_id = f"generation-run-{uuid4().hex}"
        contract = request.prompt.response_contract
        self.recorder.create_generation_run(
            GenerationRunCreate(
                id=run_id,
                project_id=project_id,
                use_case=request.prompt.use_case,
                prompt_id=request.prompt.prompt_id,
                prompt_version=request.prompt.prompt_version,
                schema_name=contract.schema_name,
                schema_version=contract.schema_version,
                requested_profile_id=options.model_profile,
                allow_fallback=options.allow_fallback,
                allow_repair=options.allow_repair,
                created_at=_utc_now(),
            )
        )
        return run_id

    def _record_success_attempt(
        self,
        run_id: str,
        index: int,
        kind: str,
        profile: ModelProfile,
        result: ModelResult,
        duration_ms: float,
    ) -> None:
        self._record_attempt(
            run_id,
            GenerationAttemptCreate(
                attempt_index=index,
                attempt_kind=kind,
                profile_id=profile.id,
                provider=result.provider_id,
                model=result.model_id,
                status="succeeded",
                duration_ms=duration_ms,
                finish_reason=result.finish_reason or "",
                input_tokens=result.usage.input_tokens,
                output_tokens=result.usage.output_tokens,
                created_at=_utc_now(),
            ),
        )

    def _record_error_attempt(
        self,
        run_id: str,
        index: int,
        kind: str,
        profile: ModelProfile,
        error: ModelGatewayError,
        duration_ms: float,
        result: ModelResult | None = None,
    ) -> None:
        self._record_attempt(
            run_id,
            GenerationAttemptCreate(
                attempt_index=index,
                attempt_kind=kind,
                profile_id=profile.id,
                provider=error.provider_id or profile.provider_id,
                model=result.model_id if result else profile.model_id,
                status="failed",
                error_code=error.code,
                retryable=error.retryable,
                duration_ms=duration_ms,
                finish_reason=(result.finish_reason or "") if result else "",
                input_tokens=result.usage.input_tokens if result else None,
                output_tokens=result.usage.output_tokens if result else None,
                created_at=_utc_now(),
            ),
        )

    def _record_attempt(self, run_id: str, create: GenerationAttemptCreate) -> None:
        if self.recorder is not None:
            self.recorder.add_generation_attempt(run_id, create)
        log_event(
            "model_attempt",
            operation=create.attempt_kind,
            run_id=run_id,
            provider=create.provider,
            model=create.model,
            result=create.status,
            error_code=create.error_code,
            retryable=create.retryable,
            duration_ms=create.duration_ms,
            attempt_index=create.attempt_index,
        )

    def _success(
        self,
        request: ModelRequest,
        result: ModelResult,
        validated: Any,
        profile: ModelProfile,
        run_id: str,
        attempt_count: int,
        repair_count: int,
        fallback_count: int,
        input_tokens: int,
        output_tokens: int,
        started: float,
    ) -> ModelExecution:
        duration_ms = _elapsed_ms(started)
        self._finish_run(
            run_id,
            GenerationRunUpdate(
                status="succeeded",
                final_profile_id=profile.id,
                provider=result.provider_id,
                model=result.model_id,
                attempt_count=attempt_count,
                repair_count=repair_count,
                fallback_count=fallback_count,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                duration_ms=duration_ms,
                completed_at=_utc_now(),
            ),
        )
        log_event(
            "model_generation_run",
            operation=request.prompt.use_case,
            project_id=str(request.metadata.get("project_id", "")),
            run_id=run_id,
            provider=result.provider_id,
            model=result.model_id,
            result="succeeded",
            attempt_count=attempt_count,
            repair_count=repair_count,
            fallback_count=fallback_count,
            duration_ms=duration_ms,
        )
        enriched = replace(
            result,
            raw_metadata={
                **result.raw_metadata,
                "generation_run_id": run_id,
                "attempt_count": attempt_count,
                "repair_count": repair_count,
                "fallback_count": fallback_count,
                "model_profile": profile.id,
            },
        )
        return ModelExecution(
            completion=ModelCompletion(request=request, result=enriched),
            generation_run_id=run_id,
            attempt_count=attempt_count,
            repair_count=repair_count,
            fallback_count=fallback_count,
            validated_value=validated,
        )

    def _finish_run(self, run_id: str, update: GenerationRunUpdate) -> None:
        if self.recorder is not None:
            self.recorder.finish_generation_run(run_id, update)


def _default_validator(request: ModelRequest) -> ContentValidator | None:
    if request.prompt.response_contract.media_type == "application/json":
        return json.loads
    return None


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 2)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def as_model_runtime(value: ModelRuntime | ModelGateway) -> ModelRuntime:
    """Keep direct workflow tests and embedders compatible with the gateway contract."""
    if isinstance(value, ModelRuntime):
        return value
    descriptor = value.describe()
    profile = ModelProfile(
        id=f"{descriptor.provider_id}.direct",
        label=f"{descriptor.provider_id} direct gateway",
        provider_id=descriptor.provider_id,
        model_id=descriptor.model_id,
        capabilities=ModelCapabilities(
            json_mode=True,
            json_schema=True,
            temperature=True,
        ),
    )
    registry = ModelGatewayRegistry()
    registry.register(descriptor.provider_id, lambda _model_id: value)
    return ModelRuntime(registry, ModelCatalog((profile,)))


__all__ = ["ModelExecution", "ModelRuntime", "as_model_runtime"]
