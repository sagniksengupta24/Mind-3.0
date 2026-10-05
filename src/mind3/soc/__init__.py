"""SoC & Interconnect subsystem for Mind 3.0."""

from .interconnect import (
    AMBAInterconnectGenerator,
    AMBAProtocol,
    ArbitrationPolicy,
    CrossbarConfig,
    MasterPortSpec,
    MemoryCompilerWrapper,
    ProtocolVIPChecker,
    SlavePortSpec,
)

__all__ = [
    "AMBAInterconnectGenerator",
    "AMBAProtocol",
    "ArbitrationPolicy",
    "CrossbarConfig",
    "MasterPortSpec",
    "MemoryCompilerWrapper",
    "ProtocolVIPChecker",
    "SlavePortSpec",
]
