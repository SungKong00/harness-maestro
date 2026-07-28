"""Reusable contracts and projections for observed work execution."""

from .contracts import (
    MAX_WORK_SPANS,
    WORK_SPAN_VERSION,
    complete_work_span,
    new_work_span,
    validate_work_span,
    validate_work_spans,
)
from .graph import build_work_graph
from .lifecycle import append_work_span, finish_work_span

__all__ = [
    "MAX_WORK_SPANS",
    "WORK_SPAN_VERSION",
    "append_work_span",
    "build_work_graph",
    "complete_work_span",
    "finish_work_span",
    "new_work_span",
    "validate_work_span",
    "validate_work_spans",
]
