"""What a scan of a layer's features found, gathered one feature at a time.

Pure Python: `scan.py` reads the QGIS objects and hands plain values over, so
the counting and every cap are testable without QGIS. Samples stop growing at
their caps while the counts keep going, so a layer of 50 000 broken polygons
costs no more memory than one of ten.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field

MAX_INVALID_SAMPLES = 10
MAX_SAMPLE_IDS = 10
MAX_DUPLICATE_GROUPS = 5
MAX_GROUP_IDS = 5
NULL = "null"
BLANK = "blank"


def missing_kind(value: object) -> str:
    """NULL for a missing value, BLANK for text with nothing but spaces, "" for a real value."""
    if value is None:
        return NULL
    if isinstance(value, str):
        return BLANK if not value.strip() else ""
    is_null = getattr(value, "isNull", None)
    if callable(is_null):
        try:
            return NULL if is_null() else ""
        except Exception:
            return ""
    return ""


@dataclass
class Bounds:
    xmin: float
    ymin: float
    xmax: float
    ymax: float

    def include(self, other: "Bounds") -> None:
        self.xmin = min(self.xmin, other.xmin)
        self.ymin = min(self.ymin, other.ymin)
        self.xmax = max(self.xmax, other.xmax)
        self.ymax = max(self.ymax, other.ymax)


@dataclass
class FieldGaps:
    null: int = 0
    blank: int = 0

    @property
    def missing(self) -> int:
        return self.null + self.blank


@dataclass
class Tally:
    """Counts and capped samples of one layer's checked features."""

    field_names: list[str]
    checked: int = 0
    invalid: int = 0
    invalid_samples: list[tuple[int, str]] = field(default_factory=list)
    empty: int = 0
    empty_ids: list[int] = field(default_factory=list)
    duplicates: int = 0
    duplicate_groups: int = 0
    group_samples: dict[bytes, list[int]] = field(default_factory=dict)
    bounds: Bounds | None = None
    gaps: list[FieldGaps] = field(default_factory=list)
    _first_with: dict[bytes, int] = field(default_factory=dict, repr=False)
    _repeated: set[bytes] = field(default_factory=set, repr=False)

    def __post_init__(self) -> None:
        if not self.gaps:
            self.gaps = [FieldGaps() for _ in self.field_names]

    def wants_reason(self) -> bool:
        """Whether the next invalid geometry still gets a sample, so its reason is worth computing."""
        return len(self.invalid_samples) < MAX_INVALID_SAMPLES

    def add_invalid(self, feature_id: int, reason: str) -> None:
        self.invalid += 1
        if self.wants_reason():
            self.invalid_samples.append((feature_id, reason))

    def add_empty(self, feature_id: int) -> None:
        self.empty += 1
        if len(self.empty_ids) < MAX_SAMPLE_IDS:
            self.empty_ids.append(feature_id)

    def add_geometry(self, feature_id: int, key: bytes) -> None:
        """Count a geometry by its normalized key; every repeat after the first is a duplicate."""
        first = self._first_with.get(key)
        if first is None:
            self._first_with[key] = feature_id
            return
        self.duplicates += 1
        if key not in self._repeated:
            self._repeated.add(key)
            self.duplicate_groups += 1
            if len(self.group_samples) < MAX_DUPLICATE_GROUPS:
                self.group_samples[key] = [first]
        group = self.group_samples.get(key)
        if group is not None and len(group) < MAX_GROUP_IDS:
            group.append(feature_id)

    def add_bounds(self, box: Bounds) -> None:
        if self.bounds is None:
            self.bounds = Bounds(box.xmin, box.ymin, box.xmax, box.ymax)
        else:
            self.bounds.include(box)

    def add_values(self, values: Sequence[object]) -> None:
        """One feature's values, in the order of `field_names`."""
        for gaps, value in zip(self.gaps, values, strict=False):
            kind = missing_kind(value)
            if kind == NULL:
                gaps.null += 1
            elif kind == BLANK:
                gaps.blank += 1

    def empty_fields(self) -> list[str]:
        """Fields without a single value among the checked features; none when nothing was checked."""
        if not self.checked:
            return []
        return [name for name, gaps in zip(self.field_names, self.gaps, strict=True) if gaps.missing >= self.checked]

    def partly_missing(self) -> list[tuple[str, FieldGaps]]:
        """Fields with some values missing but not all, the most gaps first."""
        found = [
            (name, gaps)
            for name, gaps in zip(self.field_names, self.gaps, strict=True)
            if 0 < gaps.missing < self.checked
        ]
        return sorted(found, key=lambda item: -item[1].missing)
