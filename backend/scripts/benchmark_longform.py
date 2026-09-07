"""AUD-22 reproducible read/serialization benchmark. Never accepts an existing data root.

Run from backend: uv run --frozen --extra dev python -m scripts.benchmark_longform --size small
--root is for the browser harness's newly created, empty temporary directory only.
No paid model, dispatcher, author files, or persistent app configuration is used.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import random
import sqlite3
import statistics
from tempfile import TemporaryDirectory
import time
import tracemalloc

from app.cognition.registry import CognitionRegistry
from app.data import SQLiteWritingDataStore
from app.data.unit_of_work import SqliteUnitOfWork
from app.models import (
    CanonEntityCreate,
    CharacterKnowledgeCreate,
    ManuscriptChapterCreate,
    ManuscriptProposalCreate,
    ManuscriptRevision,
    ManuscriptScene,
    ManuscriptVolumeCreate,
    ProjectCreate,
    SceneContractCreate,
    StoryFactCreate,
)
from app.narrative import NarrativeSnapshot
from app.services.backup_service import ProjectBackupService
from app.services.manuscript_service import ManuscriptService

TIERS = {"small": 20, "medium": 200, "large": 999}
STAMP = "2026-09-07T00:00:00+00:00"


def seed_project(root: Path, *, scene_count: int = 20, chars: int = 2000, revisions: int = 3):
    if not 1 <= scene_count <= 999 or not 100 <= chars <= 40000 or not 1 <= revisions <= 10:
        raise ValueError("Fixture bounds: 1–999 scenes, 100–40000 chars, 1–10 revisions.")
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()):
        raise ValueError(
            "Benchmark requires a completely empty temporary directory; author data is never overwritten."
        )
    store = SQLiteWritingDataStore(root / "app.db")
    store.init()
    project = store.create_project(
        ProjectCreate(
            title=f"Benchmark {scene_count}", premise="Synthetic letters in a foggy port."
        )
    )
    other = store.create_project(
        ProjectCreate(title="Benchmark empty comparison", premise="An isolated second project.")
    )
    rng = random.Random(20260907)
    scene_ids = []
    chapters = []
    prose_hash = hashlib.sha256()
    with SqliteUnitOfWork(store.database_path, write=True) as uow:
        for i in range(math.ceil(scene_count / 10)):
            chapter = uow.manuscripts.create_chapter(
                project.id, ManuscriptChapterCreate(sequence=i + 1, title=f"Chapter {i + 1:03}")
            )
            chapters.append(chapter)
        volumes = [
            uow.volumes.create(
                project.id, ManuscriptVolumeCreate(sequence=i + 1, title=f"Volume {i + 1}")
            )
            for i in range(math.ceil(len(chapters) / 20))
        ]
        for i, chapter in enumerate(chapters):
            uow.volumes.assign(project.id, chapter.id, volumes[i // 20].id)
        for sequence in range(1, scene_count + 1):
            scene = uow.scenes.insert(
                project.id,
                SceneContractCreate(
                    sequence=sequence,
                    title=f"Scene {sequence:04}",
                    chapter_id=chapters[(sequence - 1) // 10].id,
                    pov="Mira",
                    goal="Find the letter",
                    information_delta="An author-planned clue, not a confirmed fact.",
                ),
            )
            scene_ids.append(scene.id)
            prefix = f"合成场景{sequence:04}。"
            text = prefix + "".join(
                rng.choices(
                    "雾港灯塔旧信风雨来客停步低语邮戳海潮记忆寻路归途", k=chars - len(prefix)
                )
            )
            proposal = uow.manuscripts.create_proposal(
                project.id,
                ManuscriptProposalCreate(
                    scene_id=scene.id,
                    title=scene.title,
                    content=text,
                    context="Synthetic local benchmark context.",
                ),
            )
            uow.connection.execute(
                "UPDATE manuscript_proposals SET status = 'accepted', reviewed_at = ? WHERE id = ?",
                (STAMP, proposal.id),
            )
            for version in range(1, revisions + 1):
                content = text if version == revisions else f"修订{version}。" + text[4:]
                uow.manuscripts.insert_revision(
                    ManuscriptRevision(
                        id=f"bench-r-{sequence}-{version}",
                        project_id=project.id,
                        scene_id=scene.id,
                        proposal_id=proposal.id,
                        title=scene.title,
                        content=content,
                        version=version,
                        created_at=STAMP,
                    )
                )
            uow.manuscripts.upsert_scene(
                ManuscriptScene(
                    id=f"bench-m-{sequence}",
                    project_id=project.id,
                    scene_id=scene.id,
                    proposal_id=proposal.id,
                    title=scene.title,
                    content=text,
                    version=revisions,
                    accepted_at=STAMP,
                )
            )
            prose_hash.update(text.encode())
            fact = uow.narrative.create_fact(
                project.id,
                StoryFactCreate(
                    subject=f"Letter {sequence}",
                    predicate="arrived",
                    value=f"Synthetic fact {sequence}",
                    valid_from_scene=sequence,
                    reader_visible_from=sequence,
                    source_ref=scene.id,
                ),
            )
            uow.narrative.set_character_knowledge(
                project.id,
                fact.id,
                CharacterKnowledgeCreate(character="Mira", known_from_scene=sequence),
            )
            if sequence % 5 == 0:
                uow.canon.create(
                    project.id,
                    CanonEntityCreate(
                        entity_type="item",
                        name=f"Letter {sequence}",
                        summary="Synthetic confirmed object",
                    ),
                )
    return store, {
        "project_id": project.id,
        "project_title": project.title,
        "other_project_title": other.title,
        "scene_ids": scene_ids,
        "scene_count": scene_count,
        "chars_per_scene": chars,
        "revision_count": scene_count * revisions,
        "chapter_count": len(chapters),
        "volume_count": len(volumes),
        "fact_count": scene_count,
        "knowledge_state_count": scene_count * 3,
        "canon_count": scene_count // 5,
        "accepted_prose_chars": scene_count * chars,
        "accepted_prose_sha256_scene_order": prose_hash.hexdigest(),
    }


def samples(action, repeats: int):
    action()  # one explicit warmup; cache-cold disk IO is not measured
    values = []
    for _ in range(repeats):
        start = time.perf_counter()
        action()
        values.append((time.perf_counter() - start) * 1000)
    ordered = sorted(values)
    return {
        "n": repeats,
        "median": round(statistics.median(values), 3),
        "p95_nearest_rank": round(ordered[math.ceil(0.95 * repeats) - 1], 3),
        "max": round(max(values), 3),
    }


def peak_rss_mib():
    try:
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes

            class Counters(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
                    (name, ctypes.c_size_t)
                    for name in (
                        "PeakWorkingSetSize",
                        "WorkingSetSize",
                        "QuotaPeakPagedPoolUsage",
                        "QuotaPagedPoolUsage",
                        "QuotaPeakNonPagedPoolUsage",
                        "QuotaNonPagedPoolUsage",
                        "PagefileUsage",
                        "PeakPagefileUsage",
                    )
                ]

            value = Counters()
            value.cb = ctypes.sizeof(value)
            handle = ctypes.windll.kernel32.GetCurrentProcess
            handle.restype = wintypes.HANDLE
            info = ctypes.windll.psapi.GetProcessMemoryInfo
            info.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
            info.restype = wintypes.BOOL
            if not info(handle(), ctypes.byref(value), value.cb):
                return None
            return round(value.PeakWorkingSetSize / 1048576, 2)
        import resource

        divisor = 1048576 if platform.system() == "Darwin" else 1024
        return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / divisor, 2)
    except (ImportError, OSError, AttributeError):
        return None


def measure_backend(store, fixture, root: Path, *, repeats: int = 5):
    project = fixture["project_id"]
    service = ManuscriptService(store, CognitionRegistry([]))
    backup = ProjectBackupService(store, root / "projects")

    def raw_history():
        with store.connect() as connection:
            return connection.execute(
                "SELECT * FROM manuscript_revisions WHERE project_id = ? ORDER BY created_at DESC, id DESC",
                (project,),
            ).fetchall()

    actions = {
        "sqlite_history_raw": raw_history,
        "repository_history_dto": lambda: store.list_manuscript_revisions(project),
        "repository_scene_list": lambda: store.list_scene_contracts(project),
        "snapshot_local_no_cognition": lambda: NarrativeSnapshot.for_scene(
            project_id=project, scene_id=fixture["scene_ids"][-1], data_store=store, cognition=None
        ).render_generation_context(),
        "export_markdown": lambda: service.export(project),
        "backup_export": lambda: backup.export_package(project),
    }
    timings = {name: samples(action, repeats) for name, action in actions.items()}
    package = backup.export_package(project)
    timings["backup_preview_validation"] = samples(lambda: backup.preview_import(package), repeats)
    restored = SQLiteWritingDataStore(root / "restore.db")
    restored.init()
    importer = ProjectBackupService(restored, root / "restored-projects")
    timings["backup_restore"] = samples(
        lambda: importer.import_package(package, overwrite=True), repeats
    )
    restored_text = {
        scene.scene_id: scene.content for scene in restored.list_manuscript_scenes(project)
    }
    checksum = hashlib.sha256(
        "".join(restored_text[scene_id] for scene_id in fixture["scene_ids"]).encode()
    ).hexdigest()
    assert checksum == fixture["accepted_prose_sha256_scene_order"], (
        "Backup silently changed author prose"
    )
    assert len(restored.list_manuscript_revisions(project)) == fixture["revision_count"]
    # Allocation tracing is a separate pass, so it does not bias the above timing samples.
    tracemalloc.start()
    backup.export_package(project)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {
        "timings_ms": timings,
        "backup_bytes": len(package),
        "database_bytes": store.database_path.stat().st_size,
        "python_backup_peak_alloc_mib": round(peak / 1048576, 2),
        "python_process_peak_rss_mib": peak_rss_mib(),
        "restored_revision_count": fixture["revision_count"],
        "restored_prose_sha256": checksum,
        "environment": {
            "os": platform.platform(),
            "cpu": platform.processor(),
            "logical_cpus": os.cpu_count(),
            "python": platform.python_version(),
            "sqlite": sqlite3.sqlite_version,
        },
        "scope": "Warm local repository/service measurements. Python RSS includes seed+warmups; no dispatcher, model, module attachments, or disk-cold IO.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size", choices=TIERS, default="small")
    parser.add_argument("--root", type=Path)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    if not 1 <= args.repeats <= 20:
        parser.error("repeats must be 1–20")

    def run(root):
        store, fixture = seed_project(root, scene_count=TIERS[args.size])
        result = {
            "tier": args.size,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "fixture": fixture,
            "backend": measure_backend(store, fixture, root, repeats=args.repeats),
        }
        print(json.dumps(result, ensure_ascii=False))

    if args.root:
        run(args.root)
    else:
        with TemporaryDirectory(prefix="ai-writing-benchmark-") as directory:
            run(Path(directory))


if __name__ == "__main__":
    main()
