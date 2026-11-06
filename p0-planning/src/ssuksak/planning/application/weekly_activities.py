"""Teacher selection and split cells for a weekly activity candidate pool."""
from dataclasses import replace

from ..domain.errors import InvalidDomainValueError
from ..domain.monthly_constraint import CellState
from ..domain.provenance import (
    AuditEvent,
    AuditEventType,
    AuditHistory,
    ArrangementChange,
    GenerationMethod,
    GenerationMethodChange,
    GenerationMethodDetail,
    SplitAxis,
    TimetableChange,
    TimetableOperation,
    ValueChange,
)
from ..domain.weekly_plan import WeeklyActivityGrid, WeeklyCell
from .generate_weekly_plan import WeeklyApplicationError
from .monthly_support import require_actor, require_item_id
from .weekly_lifecycle import _WeeklyLifecycle


class WeeklyActivities(_WeeklyLifecycle):
    def __init__(self, *, id_generator, **kwargs):
        super().__init__(**kwargs)
        self._ids = id_generator

    def _target(self, plan_id, item_id, actor_id):
        plan = self._plan(plan_id)
        plan.ensure_mutable("activity")
        actor = require_actor(actor_id)
        cell = plan.find_cell(require_item_id(item_id))
        if not plan.activity_grids or cell not in plan.cells or cell.section_key != "group_activity":
            raise WeeklyApplicationError("weekly_cell_not_found", "Activity grid cell not found")
        return plan, cell, actor

    def _save(self, plan):
        plan = self._verified(plan)
        self._plans.save(plan.plan_id, plan)
        return plan

    def copy(self, plan_id, item_id, candidate_item_id, actor_id):
        plan, cell, actor = self._target(plan_id, item_id, actor_id)
        candidate = next((c for c in plan.activity_candidates if c.cell.item_id == candidate_item_id and c.cell.section_key == "group_activity"), None)
        if candidate is None or not candidate.cell.value.strip():
            raise WeeklyApplicationError("weekly_activity_candidate_invalid", "Select a non-blank activity candidate")
        value = f"[{candidate.activity_type}] {candidate.name}"
        generation = GenerationMethodDetail(GenerationMethod.RULE_ONLY, "weekly.activity_copy", "v1")
        previous = next((e.copied_from for e in reversed(cell.audit.events) if e.event_type is AuditEventType.CANDIDATE_COPIED), None)
        if (cell.value, cell.evidence, cell.generation, previous) == (value, candidate.cell.evidence, generation, candidate_item_id):
            return plan
        event = AuditEvent(AuditEventType.CANDIDATE_COPIED, self._clock.now(), plan.plan_id,
                           item_id=cell.item_id, actor_id=actor, copied_from=candidate.cell.item_id,
                           value_change=ValueChange(cell.value, value),
                           generation_change=GenerationMethodChange(cell.generation, generation))
        return self._save(plan.replace_cell(cell.item_id, replace(cell, value=value, cell_state=CellState.FILLED,
            generation=generation, evidence=candidate.cell.evidence, parent_snapshots=candidate.cell.parent_snapshots,
            source_label=candidate.activity_type, audit=cell.audit.append(event))))

    def split(self, plan_id, item_id, actor_id, *, axis, ratio=50):
        plan, cell, actor = self._target(plan_id, item_id, actor_id)
        if not isinstance(axis, SplitAxis) or type(ratio) is not int or not 10 <= ratio <= 90:
            raise WeeklyApplicationError("weekly_activity_layout_invalid", "Invalid split axis or ratio")
        now = self._clock.now()
        new_id, split_id = self._ids.new_item_id(), self._ids.new_item_id()
        new_cell = WeeklyCell(new_id, "group_activity", "", CellState.EMPTY_VALID,
            GenerationMethodDetail(GenerationMethod.RULE_ONLY, "weekly.activity_empty", "v1"),
            audit=AuditHistory((AuditEvent(AuditEventType.CREATED, now, plan.plan_id, item_id=new_id, system_actor="weekly_application"),)), day=cell.day)
        boundary = WeeklyActivityGrid(split_id=split_id, axis=axis, ratio=ratio,
                                      children=(WeeklyActivityGrid(cell=cell.item_id), WeeklyActivityGrid(cell=new_id)))
        grids = tuple(g.rebuilt(lambda n: boundary if n.cell == cell.item_id else None) for g in plan.activity_grids)
        cells = tuple(c for old in plan.cells for c in ((old, new_cell) if old.item_id == cell.item_id else (old,)))
        event = AuditEvent(AuditEventType.TIMETABLE_CHANGED, now, plan.plan_id, actor_id=actor,
            timetable_change=TimetableChange(TimetableOperation.SPLIT, split_id=split_id, axis=axis,
                                             cell_id=cell.item_id, new_cell_id=new_id))
        try:
            changed = replace(plan, cells=cells, activity_grids=grids, audit=plan.audit.append(event))
        except InvalidDomainValueError as error:
            raise WeeklyApplicationError("weekly_activity_layout_invalid", "Split exceeds the depth or width limit") from error
        return self._save(changed)

    def _indoor(self, plan_id, actor_id):
        plan = self._plan(plan_id)
        plan.ensure_mutable("indoor_play")
        actor = require_actor(actor_id)
        if not plan.indoor_play_selection:
            raise WeeklyApplicationError("weekly_activity_layout_invalid", "This Plan has no indoor candidate list")
        return plan, tuple(c for c in plan.cells if c.section_key == "indoor_play"), actor

    def _indoor_arrangement(self, plan, cells, actor, *, removed=()):
        before = tuple(c.item_id.value for c in plan.cells if c.section_key == "indoor_play")
        after = tuple(c.item_id.value for c in cells if c.section_key == "indoor_play")
        audit = plan.audit
        if before != after:
            audit = audit.append(AuditEvent(
                AuditEventType.ARRANGEMENT_CHANGED, self._clock.now(), plan.plan_id, actor_id=actor,
                arrangement_change=ArrangementChange("indoor_play", before, after),
            ))
        return self._save(replace(plan, cells=cells, audit=audit,
                                  removed_activity_cells=plan.removed_activity_cells + removed))

    def _blank_indoor(self, plan):
        item_id = self._ids.new_item_id()
        return WeeklyCell(item_id, "indoor_play", "", CellState.EMPTY_VALID,
            GenerationMethodDetail(GenerationMethod.RULE_ONLY, "weekly.indoor_empty", "v1"),
            audit=AuditHistory((AuditEvent(AuditEventType.CREATED, self._clock.now(), plan.plan_id,
                                          item_id=item_id, system_actor="weekly_application"),)))

    def add_indoor(self, plan_id, candidate_item_id, actor_id):
        plan, rows, actor = self._indoor(plan_id, actor_id)
        blank = next((c for c in rows if not c.value.strip()), None)
        candidate = None
        if candidate_item_id is not None:
            candidate_id = require_item_id(candidate_item_id)
            candidate = next((c for c in plan.activity_candidates
                              if c.cell.section_key == "indoor_play" and c.cell.item_id == candidate_id), None)
            if candidate is None or not candidate.name:
                raise WeeklyApplicationError("weekly_activity_candidate_invalid", "Select a non-blank indoor play candidate")
            if any(c.value.strip() and next((e.copied_from for e in reversed(c.audit.events)
                    if e.event_type is AuditEventType.CANDIDATE_COPIED), None) == candidate_id for c in rows):
                return plan
        elif blank is not None:
            return plan
        cell = blank or self._blank_indoor(plan)
        if candidate is not None:
            # 「[영역] 이름」 — 대·소집단과 같은 모양(Human Decision 2026-11-06, 하민). 그 전 값은 「[영역] - 이름」.
            value = f"[{candidate.activity_type}] {candidate.name}"
            generation = GenerationMethodDetail(GenerationMethod.RULE_ONLY, "weekly.activity_copy", "v1")
            event = AuditEvent(AuditEventType.CANDIDATE_COPIED, self._clock.now(), plan.plan_id,
                              item_id=cell.item_id, actor_id=actor, copied_from=candidate.cell.item_id,
                              value_change=ValueChange(cell.value, value),
                              generation_change=GenerationMethodChange(cell.generation, generation))
            cell = replace(cell, value=value, cell_state=CellState.FILLED, generation=generation,
                           evidence=candidate.cell.evidence, parent_snapshots=candidate.cell.parent_snapshots,
                           source_label=candidate.activity_type, audit=cell.audit.append(event))
        cells = tuple(cell if c is blank else c for c in plan.cells)
        if blank is None:
            at = next(i for i, c in enumerate(cells) if c is rows[-1]) + 1
            cells = cells[:at] + (cell,) + cells[at:]
        return self._indoor_arrangement(plan, cells, actor)

    def order_indoor(self, plan_id, item_ids, actor_id):
        plan, rows, actor = self._indoor(plan_id, actor_id)
        ids = tuple(require_item_id(item) for item in item_ids)
        if len(ids) != len(rows) or len(set(ids)) != len(ids) or set(ids) != {c.item_id for c in rows}:
            raise WeeklyApplicationError("weekly_activity_layout_invalid", "Order must contain every indoor play cell once")
        if ids == tuple(c.item_id for c in rows):
            return plan
        ordered = iter({c.item_id: c for c in rows}[item] for item in ids)
        cells = tuple(next(ordered) if c.section_key == "indoor_play" else c for c in plan.cells)
        return self._indoor_arrangement(plan, cells, actor)

    def remove_indoor(self, plan_id, item_id, actor_id):
        plan, rows, actor = self._indoor(plan_id, actor_id)
        item_id = require_item_id(item_id)
        cell = next((c for c in rows if c.item_id == item_id), None)
        if cell is None:
            raise WeeklyApplicationError("weekly_cell_not_found", "Indoor play cell not found")
        replacement = (self._blank_indoor(plan),) if len(rows) == 1 else ()
        cells = tuple(c for old in plan.cells for c in (replacement if old is cell else (old,)))
        return self._indoor_arrangement(plan, cells, actor, removed=(cell,))

    def remove(self, plan_id, item_id, actor_id):
        plan, cell, actor = self._target(plan_id, item_id, actor_id)
        parent = next((n for g in plan.activity_grids for n in g.boundaries() if any(c.cell == cell.item_id for c in n.children)), None)
        if parent is None:
            raise WeeklyApplicationError("weekly_activity_layout_invalid", "Keep at least one cell per day")
        sibling = next(n for n in parent.children if n.cell != cell.item_id)
        grids = tuple(g.rebuilt(lambda n: sibling if n is parent else None) for g in plan.activity_grids)
        event = AuditEvent(AuditEventType.TIMETABLE_CHANGED, self._clock.now(), plan.plan_id, actor_id=actor,
            timetable_change=TimetableChange(TimetableOperation.REMOVE, split_id=parent.split_id, axis=parent.axis, cell_id=cell.item_id))
        changed = replace(plan, cells=tuple(c for c in plan.cells if c.item_id != cell.item_id),
                          activity_grids=grids, removed_activity_cells=plan.removed_activity_cells + (cell,),
                          audit=plan.audit.append(event))
        return self._save(changed)
