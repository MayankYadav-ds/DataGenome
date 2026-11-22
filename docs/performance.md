# Observed deployment performance

Measured 2026-11-22 on Windows x64, Ryzen 7 7840HS (8 cores/16 threads), 16.4 GB RAM,
Docker Desktop/WSL2 Linux amd64. Backend budget: 2 CPUs/2 GiB; frontend 1 CPU/768 MiB;
proxy 0.5 CPU/128 MiB. Synthetic data only, local HTTPS with certificate verification
disabled explicitly in the probe. [Machine-readable results](deployment-performance.json)
come from `scripts/verify_deployment.py`; [browser results](deployment-browser-performance.json)
come from `frontend/scripts/measure-deployment.mjs`.

| Concurrent clients | Requests | Median | Exploratory p95 | Errors | Requests/s |
|---|---:|---:|---:|---:|---:|
| 1 | 30 | 18.54 ms | 36.83 ms | 0 | 11.02 |
| 2 | 30 | 18.54 ms | 22.29 ms | 0 | 14.55 |
| 5 | 30 | 25.27 ms | 2076.87 ms | 0 | 14.43 |

The endpoint is capabilities through TLS → Next → API. Thirty observations per
cohort are a small exploratory sample, not a latency SLA; the slow five-client tail
is retained. Earlier pre-final-image measurements also had a ~2.11-second five-client
p95. No ten-client or enterprise scalability claim is made.

Other single observations: demo registration 37.89 ms; upload of 4,000 synthetic
rows × 32 predictors 370.72 ms; post-restart small diagnostic 265.66 ms; its
queue-to-terminal upper bound 239.12 ms (includes execution/polling); report export
18.04 ms. A running job was observed before SIGKILL; availability returned after
2.749 seconds, that job was interrupted, dataset identity was unchanged, and a new
diagnostic completed. This is not an RTO or isolated queue-delay measurement.

After restart, the current process VmHWM was 201820 kB, current RSS 140912 kB,
and current activation cgroup peak 160952320 bytes. These are different accounting
scopes, with shared-page differences. They exclude the killed process's peak and
do not establish the full-run memory peak. Chromium's single fresh navigation had
response start 28.9 ms, DOMContentLoaded 58.8 ms, load event 212.4 ms and a CDP
heap snapshot of 4865484 bytes. This is not a Core Web Vitals measurement.

Initial cold startup, isolated SQL latency, isolated experiment timing, storage
growth and CPU utilization were **NOT MEASURED**. Experiment correctness and export
were exercised in browser scenarios, not isolated performance measurements. Native
Windows end-to-end timing is test-suite timing, not a separate load benchmark.
Benchmarks were not run concurrently with deliberate service replacement in the
reported final cohort. Earlier attempts encountered the configured rate limit and
a transient 502 during frontend replacement; neither is relabeled a passing run.

The complete nine-case native browser burst also reached the unchanged 240/minute
source-IP limit. The native CI/browser checks partition the cases into independent
synthetic workspaces (eight workflows plus the sign-in race regression). No rate
limit or assertion is disabled. An earlier HTTPS container nine-case cohort passed as one run; the final
combined burst reached HTTP 429 near the end (eight passed). Final verification
uses paced container cohorts through the real reset window. Tests are not evidence that all legitimate users will avoid rate limiting.
