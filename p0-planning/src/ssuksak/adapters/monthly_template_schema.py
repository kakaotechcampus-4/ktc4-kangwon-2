"""Boundary validation for versioned Monthly Template JSON."""

from __future__ import annotations

from ..planning.domain.errors import InvalidDomainValueError
from ..planning.domain.monthly_template import (
    DisplayMode,
    EmptyValuePolicy,
    MonthlyTemplate,
    SectionRole,
    TemplateRef,
    TemplateSection,
)


class MonthlyTemplateSchemaError(ValueError):
    pass


def _object(value: object, path: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise MonthlyTemplateSchemaError(f"{path} must be an object")
    return value


def _required(data: dict[str, object], name: str, path: str) -> object:
    if name not in data:
        raise MonthlyTemplateSchemaError(f"{path}.{name} is required")
    return data[name]


def _text(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MonthlyTemplateSchemaError(f"{path} must be non-blank")
    return value


def _boolean(value: object, path: str) -> bool:
    if type(value) is not bool:
        raise MonthlyTemplateSchemaError(f"{path} must be boolean")
    return value


def parse_monthly_template_payload(payload: object) -> MonthlyTemplate:
    root = _object(payload, "monthly_template")
    review = _object(_required(root, "review", "monthly_template"), "monthly_template.review")
    approval = _text(_required(review, "domain_owner_approval", "monthly_template.review"), "monthly_template.review.domain_owner_approval")
    runtime_active = _boolean(_required(review, "runtime_active", "monthly_template.review"), "monthly_template.review.runtime_active")
    derived_active = approval == "HUMAN_APPROVED"
    if runtime_active != derived_active:
        raise MonthlyTemplateSchemaError("runtime_active must be derived from domain_owner_approval")
    structure = _object(_required(root, "structure_rules", "monthly_template"), "monthly_template.structure_rules")
    if structure.get("global_display_mode_default") is not None:
        raise MonthlyTemplateSchemaError("global_display_mode_default must remain null")
    raw_sections = _required(root, "sections", "monthly_template")
    if not isinstance(raw_sections, list) or not raw_sections:
        raise MonthlyTemplateSchemaError("monthly_template.sections must be a non-empty array")
    sections: list[TemplateSection] = []
    try:
        for index, raw in enumerate(raw_sections):
            path = f"monthly_template.sections[{index}]"
            item = _object(raw, path)
            role = SectionRole(_text(_required(item, "role", path), f"{path}.role"))
            display = item.get("display_mode")
            policy = item.get("empty_value_policy")
            section = TemplateSection(
                section_key=_text(_required(item, "semantic_key", path), f"{path}.semantic_key"),
                role=role,
                activated=_boolean(_required(item, "activated", path), f"{path}.activated"),
                display_mode=None if display is None else DisplayMode(display),
                empty_value_policy=None if policy is None else EmptyValuePolicy(policy),
                parent_section_key=item.get("parent_section"),
                # Observed labels are evidence about the Template, not a label for
                # a concrete institution/template instance.
                source_label=item.get("source_label"),
                depth=_required(item, "depth", path),
            )
            if section.activated and role is SectionRole.CONTENT and section.display_mode is None:
                raise MonthlyTemplateSchemaError(f"{path} requires explicit display_mode")
            sections.append(section)
        return MonthlyTemplate(
            template_ref=TemplateRef(
                _text(_required(root, "template_id", "monthly_template"), "monthly_template.template_id"),
                _text(_required(root, "template_version", "monthly_template"), "monthly_template.template_version"),
            ),
            normative_status=_text(_required(root, "normative_status", "monthly_template"), "monthly_template.normative_status"),
            sections=tuple(sections),
            hierarchy_max_depth=_required(structure, "hierarchy_max_depth", "monthly_template.structure_rules"),
            default_empty_value_policy=EmptyValuePolicy(
                _text(_required(structure, "default_empty_value_policy", "monthly_template.structure_rules"), "monthly_template.structure_rules.default_empty_value_policy")
            ),
            runtime_active=derived_active,
        )
    except (InvalidDomainValueError, ValueError, TypeError) as exc:
        if isinstance(exc, MonthlyTemplateSchemaError):
            raise
        raise MonthlyTemplateSchemaError(f"Monthly Template violates the domain contract: {exc}") from exc
