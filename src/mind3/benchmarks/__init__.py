"""Mind 3.0 benchmark package.

The runner is exposed lazily so ``python -m mind3.benchmarks.runner`` does not
pre-import its target module and trigger a runpy warning.
"""

__all__ = [
    "BenchmarkRunner",
    "BenchmarkTask",
    "BenchmarkTranscript",
    "RepairTurnRecord",
]


def __getattr__(name: str):
    if name in __all__:
        from .runner import BenchmarkRunner, BenchmarkTask, BenchmarkTranscript, RepairTurnRecord
        return {
            "BenchmarkRunner": BenchmarkRunner,
            "BenchmarkTask": BenchmarkTask,
            "BenchmarkTranscript": BenchmarkTranscript,
            "RepairTurnRecord": RepairTurnRecord,
        }[name]
    raise AttributeError(name)
