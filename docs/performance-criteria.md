# Performance and release criteria

Mind 3.0 is an RTL-generation **research workbench** until it meets the
criteria below on a versioned, public holdout set. Unit-test success and
synthetic fixtures are not product-performance evidence.

| Release level | Functional pass rate | Full verified pass rate | Required evidence |
|---|---:|---:|---|
| Experimental | Report only | Report only | Reproducible logs and exact model/tool versions |
| Useful specialist tool | >=70% | >=40% | 100+ held-out tasks, negative controls, cost and latency |
| Strong specialist tool | >=80% | >=60% | Independent repeat, human review of accepted designs |
| 9/10 claim | >=85% | >=70% | Multiple benchmark families and real-user validation |

"Verified" means all required live tools ran successfully. Simulated,
skipped, or unavailable gates must never count toward these rates.
