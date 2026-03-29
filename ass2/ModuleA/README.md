# Module A

## Overview
This module contains the implementation for Module A. It features a custom database core including a B+ Tree indexing mechanism and a brute-force approach.

## Project Structure
```text
ModuleA/
├── app.py              # Main application entry point
├── requirements.txt    # Python dependencies for the module
├── routes.py           # Application routes/endpoints logic
├── report.ipynb        # Jupyter notebook containing the analysis and report
└── database/           # Custom database engine implementation
    ├── __init__.py
    ├── bplustree.py    # B+ Tree data structure implementation for indexing
    ├── bruteforce.py   # Brute-force search methods
    ├── db_manager.py   # Database manager to handle core operations
    └── table.py        # Table abstractions and operations
```

## Execution Steps

### 1. Prerequisites

Before running the application, ensure you have the following installed:
1. **Python 3.8+**
2. **Graphviz System Executable**: Required for rendering tree structures in the `report.ipynb` notebook.
   * **Windows**: Download and install from [graphviz.org](https://graphviz.org/download/). Make sure to select **"Add Graphviz to the system PATH for all users"** during installation.

### 2. Install Dependencies

Open your terminal, navigate to the `ModuleA` directory, and install the required Python packages:
```bash
cd ModuleA

# Optional: Create and activate a virtual environment
# python -m venv venv
# venv\Scripts\activate   (Windows)
# source venv/bin/activate (macOS/Linux)

pip install -r requirements.txt
```

### 3. View the Report
To view the report and analysis, open the provided Jupyter Notebook:
```bash
jupyter notebook report.ipynb
```
