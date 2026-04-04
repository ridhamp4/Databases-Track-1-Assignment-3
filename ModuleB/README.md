# Assignment 3 - Module B

This workspace contains the Module B multi-user behaviour and stress testing deliverables at the workspace root, not inside `Assignment2/`.

## What is included

- `stress_tests/module_b_stress.py` - live API harness for concurrent usage, race-condition probes, failure simulation, and load testing.
- `stress_tests/module_b_on_module_a.py` - Module B implementation that stress-tests the Module A B+Tree transaction engine directly.
- `stress_tests/locustfile.py` - Locust profile for mixed login/read/comment load testing.
- `stress_tests/module_b_results.json` - generated JSON report after each run.

## How to run

Start the backend from the Assignment2 project first:

```bash
cd Assignment2/app/backend
python app.py
```

Then run the Module B harness from the workspace root in a second terminal:

```bash
python stress_tests/module_b_stress.py --base-url http://localhost:5001
```

To run Module B directly over Module A code (engine-level concurrent/failure testing):

```bash
python stress_tests/module_b_on_module_a.py
```

This produces:

- `stress_tests/module_b_on_module_a_results.json`

To run the Locust profile, install dependencies in the workspace venv and launch:

```bash
locust -f stress_tests/locustfile.py --host http://localhost:5001 --headless -u 100 -r 25 --run-time 20s --stop-timeout 5 --csv stress_tests/locust_module_b_small --only-summary
```

Optional arguments:

- `--users` controls how many seeded accounts participate.
- `--stress-requests` controls the total number of load-test requests.
- `--stress-concurrency` controls the worker pool size.
- `--no-cleanup` keeps the temporary test posts, polls, and groups for manual inspection.

## Reported Results

The custom Python harness was run at 1000-scale for every assignment section:

| Section                | Result |
| ---------------------- | ------ |
| Concurrent Usage       | PASS   |
| Race Condition Testing | PASS   |
| Failure Simulation     | PASS   |
| Stress Testing         | PASS   |

The Locust profile was run with 100 users for 20 seconds and completed without failures:

| Metric                  | Value  |
| ----------------------- | ------ |
| Total requests          | 2734   |
| Failures                | 0      |
| Average latency         | 386 ms |
| 95th percentile latency | 750 ms |

## What the harness checks

- Atomicity: a forced database failure rolls back completely.
- Consistency: final row counts match the expected concurrent workload.
- Isolation: concurrent users can act on shared objects without corrupting state.
- Durability: committed data remains present after the requests finish.
