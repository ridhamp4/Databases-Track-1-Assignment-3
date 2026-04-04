#!/usr/bin/env bash
set -e

echo "Setting up Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

echo "Installing required packages..."
pip install -q locust requests mysql-connector-python python-dotenv
pip install -q -r Assignment2/requirements.txt

echo "Running Custom Python Stress Test Harness..."
python stress_tests/module_b_stress.py --base-url http://localhost:5001

echo "Running Locust Stress Test Profile..."
locust -f stress_tests/locustfile.py --host http://localhost:5001 --headless -u 100 -r 25 --run-time 20s --stop-timeout 5 --csv stress_tests/locust_module_b_small --only-summary

echo "Tests completed successfully."
