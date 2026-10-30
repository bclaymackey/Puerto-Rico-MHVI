"""Support ticket submission for the MHVI dashboard.

Modular home for everything ticket-related, kept separate from auth/chat code
so it can be navigated, tested, and rolled back independently:
- core.py    pure logic + Mongo: validate, create, list tickets
- db.py      tickets collection handle — one indirection point so tests can
             swap in an isolated database

Future email notification: add tickets/notify.py and one line in core.create_ticket.
No UI, callback, or storage change required for that extension.
"""
