"""Security primitives: protected targets, validators, secrets, signatures."""

from __future__ import annotations

from ningx.security.path_validator import PathCheck, PathValidator, PathVerdict
from ningx.security.process_validator import (
    FakeProcessProbe,
    ProcessCheck,
    ProcessFacts,
    ProcessProbe,
    ProcessValidator,
    PsutilProcessProbe,
)
from ningx.security.protected_targets import (
    ProtectedTargets,
    default_protected_targets,
    is_within,
    normalize_for_compare,
)
from ningx.security.secret_store import (
    InMemorySecretStore,
    SecretStore,
    SecretStoreError,
    WindowsCredentialStore,
)
from ningx.security.signature import verify_authenticode
from ningx.security.target_assessor import TargetAssessment, TargetAssessor

__all__ = [
    "FakeProcessProbe",
    "InMemorySecretStore",
    "PathCheck",
    "PathValidator",
    "PathVerdict",
    "ProcessCheck",
    "ProcessFacts",
    "ProcessProbe",
    "ProcessValidator",
    "ProtectedTargets",
    "PsutilProcessProbe",
    "SecretStore",
    "SecretStoreError",
    "TargetAssessment",
    "TargetAssessor",
    "WindowsCredentialStore",
    "default_protected_targets",
    "is_within",
    "normalize_for_compare",
    "verify_authenticode",
]
