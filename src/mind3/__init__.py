"""
Mind 3.0: Fail-closed, deterministic AI engineering agent framework.
Merges typed contracts with an 11-phase sandbox and verification pipeline.
"""

from .core.contracts import (
    ContractSynthesizer,
    InterfaceContract,
    PortDefinition,
    PortDirection,
    RTLGenerator,
    SVAProperty,
    TimingConstraint,
    VerificationHarnessGenerator,
)
from .core.driver import PhaseDriver
from .core.types import (
    AgentAction,
    PhaseEnum,
    RunCommandAction,
    RunSkillScriptAction,
    TelemetryEvent,
    TraceRecord,
    VerificationDomain,
    VerificationResult,
    WriteFileAction,
)
from .core.verifier import (
    BaseVerifier,
    IndustryReportVerifier,
    RTLVerifier,
    SiliconSignoffVerifier,
    SoftwareVerifier,
)
from .sandbox.bwrap import BubblewrapSandbox
from .sandbox.remote_eda import (
    EDARunner,
    LocalBwrapRunner,
    RemoteSSHRunner,
    get_eda_runner,
)
from .skills import Skill, SkillMatch, SkillMetadata, SkillReference, SkillRegistry, SkillRouter

__all__ = [
    "PhaseDriver",
    "BubblewrapSandbox",
    "EDARunner",
    "LocalBwrapRunner",
    "RemoteSSHRunner",
    "get_eda_runner",
    "BaseVerifier",
    "RTLVerifier",
    "SoftwareVerifier",
    "IndustryReportVerifier",
    "SiliconSignoffVerifier",
    "PhaseEnum",
    "WriteFileAction",
    "RunCommandAction",
    "RunSkillScriptAction",
    "AgentAction",
    "VerificationDomain",
    "VerificationResult",
    "TelemetryEvent",
    "TraceRecord",
    "ContractSynthesizer",
    "RTLGenerator",
    "VerificationHarnessGenerator",
    "InterfaceContract",
    "PortDefinition",
    "PortDirection",
    "SVAProperty",
    "TimingConstraint",
    "Skill",
    "SkillMatch",
    "SkillMetadata",
    "SkillReference",
    "SkillRegistry",
    "SkillRouter",
]
