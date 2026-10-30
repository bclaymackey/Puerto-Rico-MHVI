"""Flask routes for the tickets admin UI — and startup admin provisioning.

On import, any email listed in the ADMIN_EMAILS env var (comma-separated) is
automatically set to role="admin" in the users collection. Add emails to .env;
no mongosh command needed.

Registered on app.server (the Dash/Flask underlying server) exactly like
auth/routes.py. Two endpoints:

  GET  /tickets_ui            — HTML admin page (session-protected)
  POST /tickets_ui/respond    — save reply + update ticket status

No Dash involved — pure Flask HTML so it works independently of the SPA.
Access is restricted to users with role="admin" in the users collection.
"""

import os

from dotenv import load_dotenv
from flask import redirect, request

from auth.routes import current_user_id
from mongodb.client import db as _db

load_dotenv()


# ── admin provisioning ────────────────────────────────────────────────────────

def _provision_admins() -> None:
    """Set role='admin' for every email in ADMIN_EMAILS (idempotent).

    Called once at startup inside register_ticket_routes(). Safe to call
    repeatedly — uses $set so re-running is harmless.
    """
    raw = os.getenv("ADMIN_EMAILS", "")
    emails = [e.strip().lower() for e in raw.split(",") if e.strip()]
    for email in emails:
        result = _db.users.update_one(
            {"email": email},
            {"$set": {"role": "admin"}},
        )
        if result.matched_count:
            print(f"[tickets] ✅ admin provisioned: {email}")
        else:
            print(f"[tickets] ⚠️  ADMIN_EMAILS: no account found for {email}")


# ── helpers ───────────────────────────────────────────────────────────────────

def _is_admin(user_id: str | None) -> bool:
    if not user_id:
        return False
    from bson import ObjectId
    from bson.errors import InvalidId
    try:
        doc = _db.users.find_one({"_id": ObjectId(user_id)}, {"role": 1})
    except (InvalidId, TypeError):
        return False
    return (doc or {}).get("role") == "admin"


_STATUS_COLORS = {
    "open":      ("#fff3cd", "#856404"),
    "responded": ("#d1ecf1", "#0c5460"),
    "closed":    ("#d4edda", "#155724"),
}


def _badge(status: str) -> str:
    bg, fg = _STATUS_COLORS.get(status, ("#eee", "#333"))
    return (
        f'<span style="background:{bg};color:{fg};padding:2px 10px;'
        f'border-radius:12px;font-size:12px;font-weight:600">{status}</span>'
    )


def _ticket_row(t: dict) -> str:
    tid = str(t["_id"])
    created = t.get("created_at", "")
    if hasattr(created, "strftime"):
        created = created.strftime("%Y-%m-%d %H:%M UTC")
    reply_html = ""
    if t.get("reply"):
        reply_html = (
            f'<div style="margin-top:6px;padding:6px 10px;background:#f7f8fa;'
            f'border-left:3px solid #4b0082;font-size:12px;color:#444">'
            f'<strong>Reply:</strong> {t["reply"]}</div>'
        )
    form_html = ""
    if t.get("status") != "closed":
        form_html = f"""
        <form method="POST" action="/tickets_ui/respond" style="margin-top:8px">
          <input type="hidden" name="ticket_id" value="{tid}">
          <textarea name="reply" rows="2" placeholder="Write a reply…"
            style="width:100%;padding:6px 8px;border-radius:6px;border:1px solid #d7c9ea;
                   font-size:12px;box-sizing:border-box;resize:vertical">{t.get("reply", "")}</textarea>
          <div style="display:flex;gap:8px;margin-top:4px">
            <button name="new_status" value="responded"
              style="padding:5px 14px;border-radius:6px;border:none;background:#4b0082;
                     color:white;font-size:12px;cursor:pointer">Save reply</button>
            <button name="new_status" value="closed"
              style="padding:5px 14px;border-radius:6px;border:none;background:#6c757d;
                     color:white;font-size:12px;cursor:pointer">Close ticket</button>
          </div>
        </form>"""
    return f"""
    <tr>
      <td style="padding:10px 8px;vertical-align:top;font-size:12px;color:#57606a;white-space:nowrap">{created}</td>
      <td style="padding:10px 8px;vertical-align:top;font-size:12px">{t.get("email", "")}</td>
      <td style="padding:10px 8px;vertical-align:top;font-size:12px">{t.get("category", "")}</td>
      <td style="padding:10px 8px;vertical-align:top">
        <strong style="font-size:13px">{t.get("subject", "")}</strong>
        <div style="font-size:12px;color:#444;margin-top:2px">{t.get("message", "")}</div>
        {reply_html}
        {form_html}
      </td>
      <td style="padding:10px 8px;vertical-align:top;white-space:nowrap">{_badge(t.get("status", "open"))}</td>
    </tr>"""


def _page(tickets: list, filter_status: str) -> str:
    tab_style = (
        "padding:7px 18px;border-radius:8px 8px 0 0;border:1px solid #d7c9ea;"
        "border-bottom:none;cursor:pointer;font-size:13px;font-weight:600;text-decoration:none"
    )

    def _tab(label, val):
        active = (
            "background:#4b0082;color:white"
            if filter_status == val
            else "background:#f7f8fa;color:#4b0082"
        )
        return f'<a href="/tickets_ui?status={val}" style="{tab_style};{active}">{label}</a>'

    tabs = (
        f'<div style="display:flex;gap:4px;margin-bottom:-1px">'
        f'{_tab("All","all")}{_tab("Open","open")}'
        f'{_tab("Responded","responded")}{_tab("Closed","closed")}'
        f'</div>'
    )
    rows = (
        "".join(_ticket_row(t) for t in tickets)
        if tickets
        else '<tr><td colspan="5" style="padding:24px;text-align:center;color:#57606a">No tickets found.</td></tr>'
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Tickets — MHVI Admin</title>
<style>
  body{{font-family:-apple-system,"Segoe UI",system-ui,sans-serif;background:#f7f8fa;color:#1f2328;margin:0;padding:0}}
  .wrap{{max-width:1100px;margin:32px auto;padding:0 24px}}
  h1{{font-size:20px;font-weight:700;color:#31104f;margin-bottom:4px}}
  .sub{{font-size:13px;color:#57606a;margin-bottom:24px}}
  table{{width:100%;border-collapse:collapse;background:white;border-radius:10px;overflow:hidden;border:1px solid #e5e7eb}}
  thead th{{background:#4b0082;color:white;padding:10px 8px;text-align:left;font-size:13px}}
  tbody tr:nth-child(even){{background:#fafafa}}
  tbody tr:hover{{background:#f0eaf8}}
  footer{{margin-top:40px;padding-top:12px;border-top:1px solid #e5e7eb;text-align:center;font-size:12px;color:#57606a}}
</style>
</head>
<body>
<div class="wrap">
  <h1>🎫 Support Tickets</h1>
  <div class="sub">MHVI Admin Panel &nbsp;·&nbsp; <a href="/" style="color:#4b0082">← Back to dashboard</a></div>
  {tabs}
  <table>
    <thead><tr><th>Date</th><th>Email</th><th>Category</th><th>Subject / Message</th><th>Status</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>
<footer>Made with IBM Bob</footer>
</body>
</html>"""


# ── route registration ────────────────────────────────────────────────────────

def register_ticket_routes(server) -> None:
    """Attach /tickets_ui routes to the Flask server (app.server).

    Also calls _provision_admins() once at startup so ADMIN_EMAILS in .env
    are automatically granted role='admin' without any manual mongosh step.
    """
    # Skipped (with a log line) when MongoDB cannot be reached, so a database
    # outage does not stop the whole site from starting. Admins are provisioned
    # on the next restart once the database is back.
    from mongodb.client import is_available
    if is_available():
        try:
            _provision_admins()
        except Exception as exc:
            print(f"[tickets] ⚠️  admin provisioning skipped: {exc}")
    else:
        print("[tickets] ⚠️  MongoDB unreachable — admin provisioning skipped")

    @server.route("/tickets_ui")
    def tickets_ui():
        user_id = current_user_id()
        if not _is_admin(user_id):
            return redirect("/")
        filter_status = request.args.get("status", "all")
        query = {} if filter_status == "all" else {"status": filter_status}
        tickets = list(_db.tickets.find(query).sort("created_at", -1))
        return _page(tickets, filter_status)

    @server.route("/tickets_ui/respond", methods=["POST"])
    def tickets_respond():
        user_id = current_user_id()
        if not _is_admin(user_id):
            return redirect("/")
        from bson import ObjectId
        ticket_id = request.form.get("ticket_id", "")
        reply = (request.form.get("reply") or "").strip()
        new_status = request.form.get("new_status", "responded")
        if new_status not in ("responded", "closed"):
            new_status = "responded"
        try:
            _db.tickets.update_one(
                {"_id": ObjectId(ticket_id)},
                {"$set": {"reply": reply, "status": new_status}},
            )
        except Exception:
            pass
        filter_status = request.args.get("status", "all")
        return redirect(f"/tickets_ui?status={filter_status}")
