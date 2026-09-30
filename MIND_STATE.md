current_phase: P7
phase_status:
  P0: DONE
  P1: DONE
  P2: DONE
  P3: DONE
  P4: DONE
  P5: DONE
  P6: DONE
  P7: DONE
repo_root: /home/mind/Desktop/AI/Mind-3.0
test_command: PATH=/home/mind/oss-cad-suite/bin:/home/mind/.local/bin:$PATH pytest -xvs
benchmark_command: python3 scripts/run_clean_30_tasks.py
results_dir: /home/mind/Desktop/AI/artifacts/P6/run_30_results
workspaces_dir: /home/mind/Desktop/AI/artifacts/P6/run_30_results/workspaces
toolchain:
  python: 3.10.12 / 3.12.3
  ollama: 0.5.7 (qwen2.5-coder:30b)
  yosys: Yosys 0.69+77
  sby: SymbiYosys 0.69+77 (Z3 solver)
  verilator: 5.053 devel
  iverilog: 12.0 (devel)
  vvp: 12.0 (devel)
  opensta: 2.3.1
  openroad: present
pre_existing_changes: none
pre_existing_test_failures: none
changed_files:
  - src/mind3/core/driver.py
  - src/mind3/core/verifier.py
  - src/mind3/core/contracts.py
  - src/mind3/core/coverage.py
  - src/mind3/sandbox/bwrap.py
  - benchmark_scratch/run_benchmarks.py
last_commit: ""
active_defect: none
blocked_defects: []
evidence_paths:
  - artifacts/P0/toolchain.txt
  - artifacts/P0/baseline_tests.txt
  - artifacts/P0/callgraph.md
  - artifacts/P1/audit.md
  - artifacts/P2/parser_tests.txt
  - artifacts/P3/gate1_tests.txt
  - artifacts/P3/classification.md
  - artifacts/P4/gate2_mandatory_tests.txt
  - artifacts/P4/audit.md
  - artifacts/P5/coverage_tests.txt
  - artifacts/P5/coverage_audit.md
  - artifacts/P6/fresh_full_suite.txt
  - artifacts/P6/case_A.log
  - artifacts/P6/case_B.log
  - artifacts/P6/case_C.log
  - artifacts/P6/case_D.log
  - artifacts/P6/redteam.md
  - artifacts/P6/targeted_results.md
  - artifacts/P6/results.csv
  - artifacts/P7/determinism.md
  - FINAL_VERIFICATION_AUDIT.md
background_jobs: []
properties_weakened: no
tautological_fallback_remaining: no
next_action: output Section 8 final report