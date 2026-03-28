"""
db.py — Central PostgreSQL connection factory.
All modules call get_conn() instead of importing psycopg2 directly.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
import psycopg2


def get_conn():
    """Return a psycopg2 connection to the PostgreSQL database."""
    return psycopg2.connect(config.DATABASE_URL)
