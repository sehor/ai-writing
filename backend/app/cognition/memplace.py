from pathlib import Path

from app.cognition.interfaces import (
    CommittedContentEvent,
    ContextPacket,
    ModuleReport,
    ProjectCognitionSnapshot,
    WritingScope,
)
from app.models import WritebackProposalCreate


class LocalMemplaceModule:
    name = "memplace"

    def __init__(self, modules_root: Path):
        self.modules_root = modules_root

    def project_path(self, project_id: str) -> Path:
        return self.modules_root / project_id / "modules" / self.name

    def prepare_context(
        self,
        snapshot: ProjectCognitionSnapshot,
        scope: WritingScope,
    ) -> ContextPacket:
        records = snapshot.memory_records[:24]
        if not records:
            content = "No Memory / Style records are available for this project yet."
        else:
            content = "\n\n".join(
                "\n".join(
                    [
                        f"### {record.record_type}: {record.title}",
                        f"Scope: {record.scope or 'global'}",
                        f"Tags: {record.tags or 'none'}",
                        record.content,
                    ]
                )
                for record in records
            )
        return ContextPacket(
            module=self.name,
            title="Memplace style and continuity context",
            content=content,
            source_refs=[record.source_ref for record in records if record.source_ref],
        )

    def ingest_committed_content(
        self,
        snapshot: ProjectCognitionSnapshot,
        event: CommittedContentEvent,
    ) -> ModuleReport:
        project_path = self.project_path(snapshot.project.id)
        persist_sample(project_path, event)
        proposal = WritebackProposalCreate(
            target="memory_record",
            title=f"Prose sample from {event.title}",
            rationale="Confirmed writing can serve as continuity memory for later prose generation.",
            source_ref=event.source_ref,
            payload={
                "record_type": "prose_sample",
                "title": f"{event.title} prose sample",
                "scope": event.revision.scene_id if event.revision else event.source_ref,
                "content": event.content,
                "tags": "accepted manuscript, prose sample",
                "source_ref": event.source_ref,
            },
        )
        return ModuleReport(
            module=self.name,
            summary="Stored confirmed writing as a project-scoped Memplace sample and prepared one write-back proposal.",
            project_path=project_path,
            writeback_proposals=[proposal],
        )


def persist_sample(project_path: Path, event: CommittedContentEvent) -> None:
    sample_dir = project_path / "prose_samples"
    sample_dir.mkdir(parents=True, exist_ok=True)
    sample_path = sample_dir / f"{safe_slug(event.source_ref)}.md"
    sample_path.write_text(
        "\n".join(
            [
                "---",
                f"source: {event.source}",
                f"source_ref: {event.source_ref}",
                f"title: {event.title}",
                "---",
                "",
                event.content.strip(),
                "",
            ]
        ),
        encoding="utf-8",
    )


def safe_slug(value: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else "-" for char in value)
    return "-".join(part for part in cleaned.split("-") if part) or "sample"
