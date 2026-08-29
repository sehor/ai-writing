"""Explainable local style fingerprint and drift detection.

Profiles are derived only from accepted manuscript scenes. The checker reports
statistical drift and never rewrites prose automatically.
"""

from __future__ import annotations

from collections import Counter
import math
import re

from app.analysis.models import StyleDriftFinding, StyleDriftReport, StyleProfile

_SENTENCE_SPLIT = re.compile(r"[。！？!?]+")
_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n|\n")
_TOKEN_RE = re.compile(r"[A-Za-z]{3,}|[\u4e00-\u9fff]{2,4}")
_DIALOGUE_MARKERS = ("“", "”", '"', "「", "」", "『", "』")
_METAPHOR_MARKERS = ("像", "仿佛", "好似", "如同", "宛如", "as if", "like ")
_DIRECT_EXPOSITION_MARKERS = ("因为", "其实", "显然", "也就是说", "换言之", "therefore", "because ")
_MODIFIER_MARKERS = ("很", "非常", "极其", "格外", "异常", "十分", "really ", "very ", "extremely ")
_STOP_TERMS = {
    "这个",
    "那个",
    "一个",
    "他们",
    "她们",
    "我们",
    "你们",
    "自己",
    "不是",
    "没有",
    "and",
    "the",
    "that",
    "with",
    "this",
    "from",
}


def build_style_profile(project_id: str, texts: list[str], scope: str = "project") -> StyleProfile:
    nonempty = [text.strip() for text in texts if text and text.strip()]
    combined = "\n\n".join(nonempty)
    metrics = style_metrics(combined) if combined else {}
    return StyleProfile(
        project_id=project_id,
        scope=scope,
        sample_count=len(nonempty),
        character_count=len(combined),
        metrics=metrics,
        frequent_terms=frequent_terms(combined),
    )


def build_style_drift_report(
    *,
    project_id: str,
    source_ref: str,
    profile: StyleProfile,
    text: str,
) -> StyleDriftReport:
    observed = style_metrics(text)
    findings: list[StyleDriftFinding] = []
    for metric, baseline in profile.metrics.items():
        current = observed.get(metric)
        if current is None:
            continue
        relative = relative_change(baseline, current)
        absolute = abs(relative)
        if absolute < 0.35:
            continue
        severity = "critical" if absolute >= 0.8 else "warning" if absolute >= 0.5 else "info"
        findings.append(
            StyleDriftFinding(
                metric=metric,
                severity=severity,
                baseline=round(baseline, 4),
                observed=round(current, 4),
                relative_change=round(relative, 4),
                explanation=describe_drift(metric, baseline, current, relative),
            )
        )
    order = {"critical": 0, "warning": 1, "info": 2}
    findings.sort(key=lambda item: (order[item.severity], -abs(item.relative_change), item.metric))
    return StyleDriftReport(
        project_id=project_id,
        source_ref=source_ref,
        profile_scope=profile.scope,
        sample_count=profile.sample_count,
        findings=findings,
    )


def style_metrics(text: str) -> dict[str, float]:
    text = text.strip()
    if not text:
        return {}
    sentences = [item.strip() for item in _SENTENCE_SPLIT.split(text) if item.strip()]
    paragraphs = [item.strip() for item in _PARAGRAPH_SPLIT.split(text) if item.strip()]
    sentence_lengths = [len(item) for item in sentences] or [len(text)]
    paragraph_lengths = [len(item) for item in paragraphs] or [len(text)]
    chars = max(len(text), 1)
    dialogue_chars = dialogue_character_count(text)
    return {
        "avg_sentence_length": sum(sentence_lengths) / len(sentence_lengths),
        "p90_sentence_length": percentile(sentence_lengths, 0.9),
        "avg_paragraph_length": sum(paragraph_lengths) / len(paragraph_lengths),
        "dialogue_ratio": dialogue_chars / chars,
        "ellipsis_per_1k": 1000 * (text.count("……") + text.count("...") + text.count("…")) / chars,
        "question_per_1k": 1000 * (text.count("?") + text.count("？")) / chars,
        "exclamation_per_1k": 1000 * (text.count("!") + text.count("！")) / chars,
        "modifier_density": marker_density(text, _MODIFIER_MARKERS),
        "metaphor_density": marker_density(text, _METAPHOR_MARKERS),
        "direct_exposition_density": marker_density(text, _DIRECT_EXPOSITION_MARKERS),
    }


def dialogue_character_count(text: str) -> int:
    total = 0
    pairs = (("“", "”"), ("「", "」"), ("『", "』"), ('"', '"'))
    for start, end in pairs:
        if start == end:
            parts = text.split(start)
            total += sum(len(parts[index]) for index in range(1, len(parts), 2))
            continue
        cursor = 0
        while True:
            left = text.find(start, cursor)
            if left < 0:
                break
            right = text.find(end, left + len(start))
            if right < 0:
                break
            total += max(0, right - left - len(start))
            cursor = right + len(end)
    return min(total, len(text))


def marker_density(text: str, markers: tuple[str, ...]) -> float:
    lowered = text.lower()
    count = sum(lowered.count(marker.lower()) for marker in markers)
    return 1000 * count / max(len(text), 1)


def frequent_terms(text: str, limit: int = 12) -> list[str]:
    counter = Counter(
        token.lower()
        for token in _TOKEN_RE.findall(text)
        if token.lower() not in _STOP_TERMS
    )
    return [term for term, _ in counter.most_common(limit)]


def percentile(values: list[int], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(len(ordered) * quantile) - 1))
    return float(ordered[index])


def relative_change(baseline: float, observed: float) -> float:
    if abs(baseline) < 1e-9:
        return 0.0 if abs(observed) < 1e-9 else 1.0
    return (observed - baseline) / abs(baseline)


def describe_drift(metric: str, baseline: float, observed: float, relative: float) -> str:
    direction = "higher" if relative > 0 else "lower"
    percent = abs(relative) * 100
    labels = {
        "avg_sentence_length": "average sentence length",
        "p90_sentence_length": "long-sentence tail",
        "avg_paragraph_length": "average paragraph length",
        "dialogue_ratio": "dialogue share",
        "ellipsis_per_1k": "ellipsis frequency",
        "question_per_1k": "question-mark frequency",
        "exclamation_per_1k": "exclamation frequency",
        "modifier_density": "modifier-marker density",
        "metaphor_density": "metaphor-marker density",
        "direct_exposition_density": "direct-exposition marker density",
    }
    label = labels.get(metric, metric)
    return (
        f"{label} is {percent:.0f}% {direction} than the accepted-prose baseline "
        f"({baseline:.2f} → {observed:.2f}). Review whether this is intentional; no rewrite is applied."
    )
