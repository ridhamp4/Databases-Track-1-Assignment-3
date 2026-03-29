# IITGN Connect - CS 432: Databases (Assignment 2)

**Course:** CS 432 - Databases, Semester II (2025-2026)
**Institute:** Indian Institute of Technology, Gandhinagar

## Video Demonstrations

| Module | YouTube Link |
|--------|-------------|
| Module A | [MODULE-A-VIDEO-URL-HERE](INSERT-MODULE-A-VIDEO-URL-HERE) |
| Module B | [Video Demonstration Link](https://www.youtube.com/watch?v=QTxnMOmavAc) | 

## Team Members

| Name | Module | Role |
|------|--------|------|
| Laksh Jain | A | B+ Tree DBMS Engine |
| Rudra Pratap Singh | A | B+ Tree DBMS Engine |
| Parthiv Patel | B | Backend & Database Design |
| Shriniket Behera | B | RBAC & Optimization |
| Ridham Patel | B | Frontend, UI/UX & Security |

## Project Structure

```
db_track1_assignment2/
├── ModuleA/                        # Lightweight DBMS with B+ Tree Index
│   ├── database/
│   │   ├── __init__.py
│   │   ├── bplustree.py            # B+ Tree implementation (insert, delete, search, range query, visualise)
│   │   ├── bruteforce.py           # BruteForceDB baseline for benchmarking
│   │   ├── table.py                # Table abstraction over B+ Tree (schema validation, record CRUD)
│   │   └── db_manager.py           # Database manager (multiple databases and tables)
│   ├── app.py                      # Flask application factory
│   ├── routes.py                   # REST API endpoints (14 routes)
│   ├── report.ipynb                # Jupyter notebook: benchmarks, visualisations, tests
│   ├── report_images/              # Exported charts and tree visualisations
│   └── requirements.txt
│
├── ModuleB/                        # Local API Development, RBAC & Database Optimisation
│   ├── app/
│   │   ├── backend/                # Flask backend (route blueprints, db helpers, benchmarking)
│   │   └── iitgn-connect/          # React frontend (Vite, React Router)
│   ├── sql/                        # Database creation scripts, indexes, triggers, seed data
│   ├── logs/                       # Security audit logs (audit.log)
│   ├── report.ipynb                # Module B report notebook
│   ├── report_images/              # Benchmarking charts (before/after indexing)
│   ├── requirements.txt
│   └── README.md
│
├── report.tex                      # Combined LaTeX report (Module A + Module B)
└── report.pdf                      # Compiled report
```

## Module A: Lightweight DBMS with B+ Tree Index

A B+ Tree indexing engine built from scratch in Python, supporting:

- **Insertion** with automatic node splitting
- **Deletion** with borrow/merge rebalancing
- **Exact search** (O(log N))
- **Range queries** via leaf-chain traversal (O(log N + k))
- **Value storage** associating records with keys
- **Tree visualisation** using Graphviz
- **Performance benchmarking** against BruteForceDB (insertion, search, range query, deletion, memory usage)
- **Flask REST API** exposing all DBMS operations over HTTP

## Module B: Local API Development, RBAC & Database Optimisation

A full-stack web application (IITGN Connect) with:

- **22-table MySQL schema** with ISA hierarchy, cascade deletes, composite keys
- **56 RESTful API endpoints** across 10 route blueprints
- **JWT authentication** with bcrypt password hashing and email OTP verification
- **Role-Based Access Control (RBAC)**: Admin, Student, Alumni, Professor, Organization
- **Member Portfolio** with privacy controls
- **Security audit logging**: API-level (JWT error handlers) + DB-level (63 MySQL triggers detecting direct modifications)
- **SQL indexing**: 26 custom indexes with EXPLAIN ANALYZE benchmarking (up to 99.6% speedup)
- **React frontend** with role-based UI visibility
