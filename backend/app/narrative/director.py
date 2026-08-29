from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Literal

import networkx as nx

from app.data import WritingDataStore
from app.models import StoryThread, StoryThreadEvent
from app.narrative.graph import NarrativeGraph
from app.narrative.projector import NarrativeGraphProjector
from app.narrative.snapshot import NarrativeSnapshot

DirectorSeverity = Literal["info", "warning", "critical"]
DirectorLifecycleStatus = Literal[
    "planned",
    "planted",
    "developing",
    "dormant",
    "paid_off",
    "abandoned",
]

RULE_PAYOFF_OVERDUE = "DIRECTOR_PAYOFF_OVERDUE"
RULE_PREMATURE_PAYOFF = "DIRECTOR_PREMATURE_PAYOFF"
RULE_THREAD_STALLED = "DIRECTOR_THREAD_STALLED"
RULE_ISOLATED_THREAD = "DIRECTOR_ISOLATED_THREAD"
RULE_CAUSAL_CHAIN_WEAK = "DIRECTOR_CAUSAL_CHAIN_WEAK"
RULE_GRAPH_COMMUNITY = "DIRECTOR_GRAPH_COMMUNITY_SUGGESTION"

DORMANT_AFTER_SCENES = 5
_PROGRESS_ACTIONS = {"reinforce", "misdirect", "escalate", "partial_payoff", "payoff"}
_DEVELOPMENT_ACTIONS = {"reinforce", "misdirect", "escalate", "partial_payoff"}
_ACTIVE_STATUSES = {"planted", "developing", "dormant"}


@dataclass(frozen=True)
class DirectorEvidence:
    ref: str
    kind: str
    scene_id: str = ""
    scene_sequence: int | None = None
    detail: str = ""


@dataclass(frozen=True)
class DirectorThreadLifecycle:
    thread_id: str
    title: str
    status: DirectorLifecycleStatus
    database_status: str
    status_basis: str
    history_exact: bool
    planted_scene: int | None = None
    last_event_id: str = ""
    last_event_scene: int | None = None
    payoff_scene: int | None = None
    detail: str = ""


@dataclass(frozen=True)
class DirectorFinding:
    code: str
    severity: DirectorSeverity
    title: str
    detail: str
    thread_ids: tuple[str, ...] = ()
    node_ids: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()
    evidence: tuple[DirectorEvidence, ...] = ()
    data: dict[str, Any] = field(default_factory=dict)
    advisory: bool = True


@dataclass(frozen=True)
class DirectorCommunitySuggestion:
    id: str
    node_ids: tuple[str, ...]
    thread_ids: tuple[str, ...]
    detail: str


@dataclass(frozen=True)
class DirectorReport:
    project_id: str
    scene_id: str
    scene_sequence: int
    thread_lifecycles: tuple[DirectorThreadLifecycle, ...]
    findings: tuple[DirectorFinding, ...]
    communities: tuple[DirectorCommunitySuggestion, ...] = ()


class DirectorAnalyzer:
    """Deterministic, read-only narrative analytics for one scene boundary."""

    def __init__(self, data_store: WritingDataStore):
        self.data_store = data_store

    def for_scene(self, *, project_id: str, scene_id: str) -> DirectorReport:
        snapshot = NarrativeSnapshot.for_scene(
            project_id=project_id,
            scene_id=scene_id,
            data_store=self.data_store,
        )
        graph = NarrativeGraphProjector(self.data_store).project(project_id)
        return self.analyze_scene(snapshot, graph)

    def analyze_scene(
        self,
        snapshot: NarrativeSnapshot,
        graph: NarrativeGraph | None = None,
    ) -> DirectorReport:
        graph = graph or NarrativeGraphProjector(self.data_store).project(snapshot.project.id)
        scene_graph = _scene_graph(snapshot, graph)
        sequence_by_scene = snapshot.scene_sequence_by_id
        events_by_thread = _events_by_thread(snapshot.thread_event_history, sequence_by_scene)
        threads = sorted(snapshot.story_threads, key=lambda item: (-item.importance, item.id))

        lifecycles = tuple(
            _lifecycle_for_thread(
                thread,
                events_by_thread.get(thread.id, ()),
                current_scene=snapshot.scene.sequence,
                latest_scene=snapshot.latest_scene_sequence,
            )
            for thread in threads
        )
        findings: list[DirectorFinding] = []
        for thread, lifecycle in zip(threads, lifecycles, strict=True):
            thread_events = events_by_thread.get(thread.id, ())
            findings.extend(
                _thread_findings(
                    thread,
                    lifecycle,
                    thread_events,
                    current_scene=snapshot.scene.sequence,
                )
            )
            findings.extend(_structural_findings(thread, lifecycle, thread_events, scene_graph))

        communities = _community_suggestions(scene_graph, threads)
        findings.extend(_community_findings(communities))
        findings.sort(key=_finding_sort_key)
        return DirectorReport(
            project_id=snapshot.project.id,
            scene_id=snapshot.scene.id,
            scene_sequence=snapshot.scene.sequence,
            thread_lifecycles=lifecycles,
            findings=tuple(findings),
            communities=communities,
        )


def _events_by_thread(
    events: list[StoryThreadEvent],
    sequence_by_scene: dict[str, int],
) -> dict[str, tuple[tuple[int, StoryThreadEvent], ...]]:
    grouped: dict[str, list[tuple[int, StoryThreadEvent]]] = defaultdict(list)
    for event in events:
        sequence = sequence_by_scene.get(event.scene_id)
        if sequence is None:
            continue
        grouped[event.thread_id].append((sequence, event))
    return {
        thread_id: tuple(sorted(items, key=lambda item: (item[0], item[1].id)))
        for thread_id, items in grouped.items()
    }


def _lifecycle_for_thread(
    thread: StoryThread,
    events: tuple[tuple[int, StoryThreadEvent], ...],
    *,
    current_scene: int,
    latest_scene: int,
) -> DirectorThreadLifecycle:
    planted_events = [(sequence, event) for sequence, event in events if event.action == "plant"]
    payoff_events = [(sequence, event) for sequence, event in events if event.action == "payoff"]
    development_events = [
        (sequence, event) for sequence, event in events if event.action in _DEVELOPMENT_ACTIONS
    ]
    progress_events = [
        (sequence, event) for sequence, event in events if event.action in _PROGRESS_ACTIONS
    ]
    planted_scene = (
        min(sequence for sequence, _ in planted_events)
        if planted_events
        else thread.planted_at
        if thread.planted_at is not None and thread.planted_at < current_scene
        else None
    )
    last_sequence, last_event = events[-1] if events else (None, None)

    if payoff_events:
        payoff_scene, _ = payoff_events[0]
        return DirectorThreadLifecycle(
            thread_id=thread.id,
            title=thread.title,
            status="paid_off",
            database_status=thread.status,
            status_basis="payoff_event",
            history_exact=True,
            planted_scene=planted_scene,
            last_event_id=last_event.id if last_event else "",
            last_event_scene=last_sequence,
            payoff_scene=payoff_scene,
            detail=f"A payoff event occurred at scene {payoff_scene} before scene {current_scene}.",
        )

    if planted_scene is None:
        if thread.status == "abandoned" and current_scene >= latest_scene:
            return DirectorThreadLifecycle(
                thread_id=thread.id,
                title=thread.title,
                status="abandoned",
                database_status=thread.status,
                status_basis="current_status",
                history_exact=False,
                detail=(
                    "The authoritative current status is abandoned, but the domain has no "
                    "abandonment scene timestamp, so historical timing is unknown."
                ),
            )
        return DirectorThreadLifecycle(
            thread_id=thread.id,
            title=thread.title,
            status="planned",
            database_status=thread.status,
            status_basis="event_history",
            history_exact=True,
            last_event_id=last_event.id if last_event else "",
            last_event_scene=last_sequence,
            detail=f"No plant event is visible before scene {current_scene}.",
        )

    if thread.status == "abandoned" and current_scene >= latest_scene:
        return DirectorThreadLifecycle(
            thread_id=thread.id,
            title=thread.title,
            status="abandoned",
            database_status=thread.status,
            status_basis="current_status",
            history_exact=False,
            planted_scene=planted_scene,
            last_event_id=last_event.id if last_event else "",
            last_event_scene=last_sequence,
            detail=(
                "The authoritative current status is abandoned, but no abandonment scene is "
                "stored. It is applied only at the latest known scene and is not backdated."
            ),
        )

    last_progress_scene = max((sequence for sequence, _ in progress_events), default=planted_scene)
    inactive_scenes = current_scene - last_progress_scene
    historical_status_note = (
        " Current database status is abandoned, but it is not backdated because the domain "
        "stores no abandonment scene timestamp."
        if thread.status == "abandoned" and current_scene < latest_scene
        else ""
    )
    if inactive_scenes >= DORMANT_AFTER_SCENES:
        return DirectorThreadLifecycle(
            thread_id=thread.id,
            title=thread.title,
            status="dormant",
            database_status=thread.status,
            status_basis="inactivity_threshold",
            history_exact=True,
            planted_scene=planted_scene,
            last_event_id=last_event.id if last_event else "",
            last_event_scene=last_sequence,
            detail=(
                f"No structured progress event occurred for {inactive_scenes} scene(s); "
                f"the deterministic dormant threshold is {DORMANT_AFTER_SCENES}."
                f"{historical_status_note}"
            ),
        )

    if development_events:
        return DirectorThreadLifecycle(
            thread_id=thread.id,
            title=thread.title,
            status="developing",
            database_status=thread.status,
            status_basis="event_history",
            history_exact=True,
            planted_scene=planted_scene,
            last_event_id=last_event.id if last_event else "",
            last_event_scene=last_sequence,
            detail=(
                "A reinforce, misdirect, escalate, or partial payoff event has occurred."
                f"{historical_status_note}"
            ),
        )
    return DirectorThreadLifecycle(
        thread_id=thread.id,
        title=thread.title,
        status="planted",
        database_status=thread.status,
        status_basis="event_history",
        history_exact=True,
        planted_scene=planted_scene,
        last_event_id=last_event.id if last_event else "",
        last_event_scene=last_sequence,
        detail=(
            f"The thread has been planted but has no later development before scene {current_scene}."
            f"{historical_status_note}"
        ),
    )


def _thread_findings(
    thread: StoryThread,
    lifecycle: DirectorThreadLifecycle,
    events: tuple[tuple[int, StoryThreadEvent], ...],
    *,
    current_scene: int,
) -> list[DirectorFinding]:
    findings: list[DirectorFinding] = []
    payoff_events = [(sequence, event) for sequence, event in events if event.action == "payoff"]
    progress_events = [
        (sequence, event) for sequence, event in events if event.action in _PROGRESS_ACTIONS
    ]

    if (
        lifecycle.status in _ACTIVE_STATUSES
        and thread.target_payoff_to is not None
        and current_scene >= thread.target_payoff_to
    ):
        last_progress_scene, last_progress_event = (
            progress_events[-1] if progress_events else (lifecycle.planted_scene, None)
        )
        evidence = (
            (
                DirectorEvidence(
                    ref=last_progress_event.id,
                    kind="story_thread_event",
                    scene_id=last_progress_event.scene_id,
                    scene_sequence=last_progress_scene,
                    detail=f"Latest progress action: {last_progress_event.action}.",
                ),
            )
            if last_progress_event
            else ()
        )
        overdue_by = current_scene - thread.target_payoff_to
        findings.append(
            DirectorFinding(
                code=RULE_PAYOFF_OVERDUE,
                severity="critical" if thread.importance >= 4 else "warning",
                title=f"Story thread payoff is overdue: {thread.title}",
                detail=(
                    f"At scene {current_scene}, the target payoff window "
                    f"{thread.target_payoff_from or '?'}-{thread.target_payoff_to} has ended, "
                    "no payoff event is visible, and the thread remains active."
                ),
                thread_ids=(thread.id,),
                node_ids=(f"thread:{thread.id}",),
                source_refs=tuple(item.ref for item in evidence),
                evidence=evidence,
                data={
                    "current_scene": current_scene,
                    "target_payoff_from": thread.target_payoff_from,
                    "target_payoff_to": thread.target_payoff_to,
                    "last_progress_scene": last_progress_scene,
                    "overdue_by": overdue_by,
                },
            )
        )

    if payoff_events and thread.target_payoff_from is not None:
        payoff_scene, payoff_event = payoff_events[0]
        if payoff_scene < thread.target_payoff_from:
            early_by = thread.target_payoff_from - payoff_scene
            evidence = DirectorEvidence(
                ref=payoff_event.id,
                kind="story_thread_event",
                scene_id=payoff_event.scene_id,
                scene_sequence=payoff_scene,
                detail="Structured payoff event.",
            )
            findings.append(
                DirectorFinding(
                    code=RULE_PREMATURE_PAYOFF,
                    severity="warning",
                    title=f"Story thread pays off before its target window: {thread.title}",
                    detail=(
                        f"The payoff occurs at scene {payoff_scene}, {early_by} scene(s) before "
                        f"the target window opens at scene {thread.target_payoff_from}."
                    ),
                    thread_ids=(thread.id,),
                    node_ids=(f"thread:{thread.id}",),
                    source_refs=(payoff_event.id,),
                    evidence=(evidence,),
                    data={
                        "actual_payoff_scene": payoff_scene,
                        "target_payoff_from": thread.target_payoff_from,
                        "early_by": early_by,
                    },
                )
            )

    if lifecycle.status == "dormant":
        last_progress_scene, last_progress_event = (
            progress_events[-1] if progress_events else (lifecycle.planted_scene, None)
        )
        inactive_scenes = current_scene - (last_progress_scene or current_scene)
        evidence = (
            (
                DirectorEvidence(
                    ref=last_progress_event.id,
                    kind="story_thread_event",
                    scene_id=last_progress_event.scene_id,
                    scene_sequence=last_progress_scene,
                    detail=f"Latest progress action: {last_progress_event.action}.",
                ),
            )
            if last_progress_event
            else ()
        )
        findings.append(
            DirectorFinding(
                code=RULE_THREAD_STALLED,
                severity="warning" if thread.importance >= 3 else "info",
                title=f"Story thread has stalled: {thread.title}",
                detail=(
                    f"No structured progress has occurred for {inactive_scenes} scene(s); "
                    f"the dormant threshold is {DORMANT_AFTER_SCENES}."
                ),
                thread_ids=(thread.id,),
                node_ids=(f"thread:{thread.id}",),
                source_refs=tuple(item.ref for item in evidence),
                evidence=evidence,
                data={
                    "last_progress_scene": last_progress_scene,
                    "inactive_scenes": inactive_scenes,
                    "threshold": DORMANT_AFTER_SCENES,
                    "importance": thread.importance,
                },
            )
        )
    return findings


def _scene_graph(snapshot: NarrativeSnapshot, graph: NarrativeGraph) -> nx.MultiDiGraph:
    active_relation_ids = {relation.id for relation in snapshot.narrative_relations}
    scene_graph = nx.MultiDiGraph(project_id=snapshot.project.id, scene=snapshot.scene.sequence)
    for source, target, key, data in graph.networkx.edges(keys=True, data=True):
        if key not in active_relation_ids:
            continue
        scene_graph.add_node(source, **graph.networkx.nodes[source])
        scene_graph.add_node(target, **graph.networkx.nodes[target])
        scene_graph.add_edge(source, target, key=key, **data)
    return scene_graph


def _structural_findings(
    thread: StoryThread,
    lifecycle: DirectorThreadLifecycle,
    events: tuple[tuple[int, StoryThreadEvent], ...],
    graph: nx.MultiDiGraph,
) -> list[DirectorFinding]:
    if lifecycle.status in {"planned", "abandoned"}:
        return []
    thread_node = f"thread:{thread.id}"
    event_nodes = tuple(f"event:{event.id}" for _, event in events)
    candidate_nodes = (thread_node, *event_nodes)
    present_nodes = tuple(node for node in candidate_nodes if node in graph)
    if not present_nodes:
        return [
            DirectorFinding(
                code=RULE_ISOLATED_THREAD,
                severity="warning" if thread.importance >= 4 else "info",
                title=f"Story thread is structurally isolated: {thread.title}",
                detail=(
                    "No scene-valid NarrativeRelation connects the thread or its visible events "
                    "to the Narrative Graph. This is an advisory structural signal, not story truth."
                ),
                thread_ids=(thread.id,),
                node_ids=candidate_nodes,
                data={"relation_count": 0},
            )
        ]

    connected: set[str] = set()
    for node in present_nodes:
        connected.update(nx.ancestors(graph, node))
        connected.update(nx.descendants(graph, node))
        connected.update(graph.predecessors(node))
        connected.update(graph.successors(node))
    external = sorted(node for node in connected if node not in candidate_nodes)
    if external:
        return []
    return [
        DirectorFinding(
            code=RULE_CAUSAL_CHAIN_WEAK,
            severity="warning" if thread.importance >= 4 else "info",
            title=f"Story thread has no external causal path: {thread.title}",
            detail=(
                "Thread/event nodes exist in the scene-valid graph but do not reach any external "
                "narrative node. Treat this as a structural review signal only."
            ),
            thread_ids=(thread.id,),
            node_ids=tuple(sorted(present_nodes)),
            data={"external_path_nodes": 0},
        )
    ]


def _community_suggestions(
    graph: nx.MultiDiGraph,
    threads: list[StoryThread],
) -> tuple[DirectorCommunitySuggestion, ...]:
    if graph.number_of_nodes() < 2 or graph.number_of_edges() == 0:
        return ()
    simple = nx.Graph()
    simple.add_nodes_from(graph.nodes)
    simple.add_edges_from((source, target) for source, target in graph.edges())
    communities = [
        tuple(sorted(community))
        for community in nx.algorithms.community.greedy_modularity_communities(simple)
        if len(community) >= 2
    ]
    communities.sort(key=lambda nodes: (-len(nodes), nodes))
    thread_by_node = {f"thread:{thread.id}": thread.id for thread in threads}
    return tuple(
        DirectorCommunitySuggestion(
            id=f"community-{index + 1}",
            node_ids=nodes,
            thread_ids=tuple(
                sorted(thread_by_node[node] for node in nodes if node in thread_by_node)
            ),
            detail=(
                "NetworkX structural grouping for review only; it does not define an Arc or "
                "modify any StoryThread."
            ),
        )
        for index, nodes in enumerate(communities)
    )


def _community_findings(
    communities: tuple[DirectorCommunitySuggestion, ...],
) -> list[DirectorFinding]:
    return [
        DirectorFinding(
            code=RULE_GRAPH_COMMUNITY,
            severity="info",
            title=f"Graph community suggestion: {community.id}",
            detail=community.detail,
            thread_ids=community.thread_ids,
            node_ids=community.node_ids,
            data={"node_count": len(community.node_ids)},
        )
        for community in communities
    ]


def _finding_sort_key(finding: DirectorFinding) -> tuple[int, str, tuple[str, ...], str]:
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    return (
        severity_order[finding.severity],
        finding.code,
        finding.thread_ids,
        finding.title,
    )
