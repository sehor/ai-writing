"""Describe the actual dispatcher path; configured providers are never auto-enabled."""

from app.integrations.knowledge_compiler import DisabledKnowledgeCompiler
from app.integrations.llmwiki_clp import UnavailableKnowledgeCompiler
from app.outbox.handlers import OutboxJobContext
from app.outbox.models import AnalysisExecution, OutboxJob


def execution_evidence(
    context: OutboxJobContext, job: OutboxJob, *, failed: bool = False
) -> AnalysisExecution:
    source = str(job.payload.get("source_ref") or f"{job.aggregate_type}:{job.aggregate_id}")
    if job.job_type == "consistency_analysis":
        result = AnalysisExecution(
            mode="local_rules",
            processor="local_consistency",
            outcome="limited",
            source_ref=source,
            limitations="仅本地文本规则；零问题不代表完整语义无矛盾。未执行模型语义审稿。",
        )
    elif job.job_type == "writeback_analysis":
        result = AnalysisExecution(
            mode="local_cognition",
            processor="local_writeback",
            outcome="limited",
            source_ref=source,
            limitations="本地 cognition 生成待审核候选；未自动调用 Provider，不直接写入 Canon。",
        )
    elif job.job_type == "clp_extraction":
        compiler = context.compiler
        disabled = compiler is None or isinstance(compiler, DisabledKnowledgeCompiler)
        unavailable = isinstance(compiler, UnavailableKnowledgeCompiler)
        result = AnalysisExecution(
            mode="not_configured" if disabled else "unavailable" if unavailable else "external_clp",
            processor=compiler.compiler_version if compiler else "disabled",
            outcome="not_executed" if disabled else "completed",
            source_ref=source,
            limitations="CLP 未配置，未执行抽取。"
            if disabled
            else "CLP 配置不可用；正文已保存，可修复配置并重试。"
            if unavailable
            else "外部 CLP 仅提供有来源的候选，须人工审核；不是完整语义审稿或模型效果认证。",
        )
    else:
        result = AnalysisExecution(
            mode="index",
            processor=type(context.wiki).__name__,
            outcome="completed",
            source_ref=source,
            limitations="仅 Wiki 索引，不是正文正确性检查。",
        )
    if failed:
        result.outcome = "failed"
    return result
