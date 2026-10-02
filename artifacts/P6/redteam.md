# Red Team False-PASS Resistance Audit

| Vector | Attempt Description | Expected | Observed Status | False PASS? |
|---|---|---|---|---|
| Buggy Combinational RTL | XOR/subtract instead of addition | FAIL | FORMAL_INVARIANT_BREACH | NO (IMMUNE) |
| Buggy Sequential RTL | Reset to 0xE instead of 0x0 | FAIL | FORMAL_INVARIANT_BREACH | NO (IMMUNE) |
| Unsupported Formal Property | req ##[2:4] gnt unsupported construct | FAIL | UNSUPPORTED_FORMAL_PROPERTY | NO (IMMUNE) |
| Tool Made Unavailable via PATH | Stripped yosys/sby from PATH | FAIL | EDA_BINARY_MISSING | NO (IMMUNE) |
| Forced Exception in Gate Execution | Runner raises unhandled RuntimeError | FAIL | EXCEPTION_CAUGHT: RuntimeError | NO (IMMUNE) |
| Empty Property Set | Contract with zero SVA properties passed to formal signoff | FAIL | EMPTY_FORMAL_PROPERTY_SET | NO (IMMUNE) |
| Mock Flag in Benchmark Path | Audit benchmark harness for allow_mock_fallback=True | FAIL | allow_mock_fallback=False strictly enforced in run_benchmarks.py | NO (IMMUNE) |

## Summary
- Total attack vectors tested: 7
- False PASS observed: 0
- Immunity: **100% FAIL-CLOSED**
