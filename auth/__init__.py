"""Self-hosted email + password authentication for the MHVI dashboard.

Modular home for everything auth-related, kept separate from chat/dashboard code
so it can be navigated, tested, and rolled back independently:
- core.py    pure logic + Mongo: password hashing, sessions, signup/login/me
- db.py      auth collection handles (users, auth_sessions) — one indirection point
             so tests can swap in an isolated database

Flask routes (routes.py) and Dash wiring live outside this package's pure core.
"""
