from __future__ import annotations

import pytest
from ssuksak.planning.domain.errors import DomainError, InvalidIdentifierError
from ssuksak.planning.domain.identifiers import ActorId, ItemId, PlanId


@pytest.mark.parametrize("identifier_type", [PlanId, ItemId, ActorId])
@pytest.mark.parametrize("invalid", ["", "   ", None, 123])
def test_identifier_rejects_blank_or_non_string_values(identifier_type, invalid):
    with pytest.raises(InvalidIdentifierError):
        identifier_type(invalid)


@pytest.mark.parametrize("identifier_type", [PlanId, ItemId, ActorId])
def test_identifier_is_an_immutable_value_object(identifier_type):
    left = identifier_type("opaque_001")
    right = identifier_type("opaque_001")

    assert left == right
    assert hash(left) == hash(right)
    assert str(left) == "opaque_001"
    with pytest.raises(AttributeError):
        left.value = "changed"


def test_invalid_identifier_is_a_domain_error():
    with pytest.raises(DomainError):
        PlanId("")
