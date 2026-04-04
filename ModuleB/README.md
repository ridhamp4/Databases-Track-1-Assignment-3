# Assignment 3 - Module B

This workspace contains the Module B multi-user behaviour and stress testing deliverables at the workspace root, not inside `Assignment2/`.

## What is included

- `stress_tests/module_b_stress.py` - live API harness for concurrent usage, race-condition probes, failure simulation, and load testing.
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

Optional arguments:

- `--users` controls how many seeded accounts participate.
- `--stress-requests` controls the total number of load-test requests.
- `--stress-concurrency` controls the worker pool size.
- `--no-cleanup` keeps the temporary test posts, polls, and groups for manual inspection.

## What the harness checks

- Atomicity: a forced database failure rolls back completely.
- Consistency: final row counts match the expected concurrent workload.
- Isolation: concurrent users can act on shared objects without corrupting state.
- Durability: committed data remains present after the requests finish.
