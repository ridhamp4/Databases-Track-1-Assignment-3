# Databases – Assignment 3

**Team name:** chernaugh

This repository contains **Assignment 3** deliverables for:

- **Module A:** Demonstrate that the Assignment-2 B+Tree mini-database satisfies **ACID** properties.
- **Module B:** Test ACID-related behaviour **from the application/API perspective** on the Assignment-2 backend (concurrency, race probes, failure simulation, stress testing), including a tool-based stress run (Locust).

## Video Links

- **Module A video (ACID over B+Tree):** <ADD_LINK_HERE>
- **Module B video (API/application testing + Locust):** <ADD_LINK_HERE>

> Replace the placeholders with your final uploaded/unlisted video URLs.

## Team Members & Contributions

- **Parthiv Patel** — Worked on Module A (engine + ACID validation) and report/video material.
- **Laksh Jain** — Worked on Module A (B+Tree storage + integration) and report/video material.
- **Shriniket Behera** — Worked on Module A (constraints/consistency + isolation/durability validation) and report/video material.
- **Ridham Patel** — Worked on Module B (API/application stress harness + Locust) and report/video material.
- **Rudra Pratap Singh** — Worked on Module B (concurrency/race/failure simulation testing) and report/video material.

## Repository Structure

- `ModuleA/` — B+Tree mini DB + transaction manager + ACID tests
- `ModuleB/` — Assignment2 backend (for demo) + Module B stress tests
- `assignment3_report.tex` / `assignment3_report.pdf` — submission report
- `video_explanation_script.md` — 5-member speaking scripts for the demo video

For additional details, see `ModuleA/README.md` and `ModuleB/README.md`.

## Module A (B+Tree Engine) — What we test

Module A proves ACID properties at the database-engine level.

**Key code:**

- `ModuleA/database/bplustree.py` (storage)
- `ModuleA/database/table.py` (table API + constraints)
- `ModuleA/database/transaction.py` (WAL, commit/rollback, recovery)
- `ModuleA/database/db_manager.py` (integration + isolation lock)

### Run Module A tests (ACID)

From the workspace root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r ModuleA/requirements.txt

cd ModuleA
python test/Atomicity.py --mode crash
python test/Atomicity.py --mode verify
python test/Consistency.py
python test/Isolation.py
python test/Durability.py
python test/multi_relation_transaction_demo.py --mode commit
python test/multi_relation_transaction_demo.py --mode verify
```

Expected output: each test prints **PASS/FAIL** with details on failure.

## Module B (Assignment2 Backend) — What we test

Module B validates multi-user safety and failure handling **through the application/API**, as required:

- **Concurrent usage:** many users perform operations concurrently on shared artifacts.
- **Race condition testing:** repeated concurrent attempts for like/vote/join; verify no duplicates.
- **Failure simulation:** deliberate SQL failure mid-transaction; verify rollback leaves no partial rows.
- **Stress testing:** high-volume requests; observe correctness + latency; includes tool-based stress via **Locust**.

### Start backend (Terminal 1)

Module B runs against the **Assignment 2 backend**. Follow the backend setup in `ModuleB/Assignment2/README.md` (MySQL + `.env`).

```bash
source .venv/bin/activate
pip install -r ModuleB/Assignment2/requirements.txt

cd ModuleB/Assignment2/app/backend
python seed.py
python app.py
```

Backend default URL used by the harness: `http://localhost:5001`

### Run API/application harness (Terminal 2)

```bash
source .venv/bin/activate
python ModuleB/stress_tests/module_b_stress.py --base-url http://localhost:5001
```

Output artifacts:

- `ModuleB/stress_tests/module_b_results.json`

### Run Locust (tool-based stress)

```bash
source .venv/bin/activate
pip install locust

cd ModuleB
locust -f stress_tests/locustfile.py --host http://localhost:5001 --headless \
	-u 100 -r 25 --run-time 20s --stop-timeout 5 --csv stress_tests/locust_module_b --only-summary
```

CSV outputs are written under `ModuleB/stress_tests/` (e.g., `locust_module_b_stats.csv`).

## Notes for Evaluation Mapping

- **Correctness of transaction behaviour:** Module A tests + WAL recovery.
- **Failure handling:** Module A crash/rollback; Module B forced SQL failure + rollback verification.
- **Multi-user safety/isolation:** Module A isolation test; Module B concurrency + race probes.
- **DB ↔ B+Tree consistency:** Module A stores records only in B+Tree; Table operations and recovery apply directly to B+Tree.
- **Robustness under load:** Module B stress phase + Locust.
