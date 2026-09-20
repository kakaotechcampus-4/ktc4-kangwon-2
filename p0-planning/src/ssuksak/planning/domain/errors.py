"""Errors raised when a Planning Core invariant is violated."""


class DomainError(Exception):
    """Base class for expected domain failures."""


class InvalidDomainValueError(DomainError, ValueError):
    """A value cannot represent a valid domain concept."""


class InvalidIdentifierError(InvalidDomainValueError):
    """An opaque identifier is blank or has an invalid type."""


class InvalidStateTransitionError(DomainError):
    """A requested state transition is not allowed."""
