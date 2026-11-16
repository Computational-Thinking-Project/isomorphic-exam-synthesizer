"""In-memory RPC stub for Python contract tests, not a database lock simulator.

Table access is read-only. The small approval transition represents a successful
RPC receipt; transaction, ACL and concurrency guarantees require real PostgreSQL.
"""

from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace


class Query:
    def __init__(self, state, name):
        self.state, self.name = state, name
        self.filters = []
        self.maximum = None
        self.selected_columns = None

    def select(self, *args, **_kwargs):
        if args and isinstance(args[0], str) and args[0].strip() != "*":
            self.selected_columns = [c.strip() for c in args[0].split(",") if c.strip()]
        return self

    def eq(self, field, value):
        self.filters.append((field, value))
        return self

    def in_(self, field, values):
        self.filters.append((field, values))
        return self

    def limit(self, value):
        self.maximum = value
        return self

    def execute(self):
        def matches(row):
            for field, expected in self.filters:
                if field == "exam_versions.session_id":
                    version = next(
                        (
                            v
                            for v in self.state.get("exam_versions", [])
                            if v.get("id") == row.get("version_id")
                        ),
                        {},
                    )
                    actual = version.get("session_id")
                else:
                    actual = row.get(field)
                if isinstance(expected, list):
                    if actual not in expected:
                        return False
                elif actual != expected:
                    return False
            return True

        rows = [deepcopy(row) for row in self.state.get(self.name, []) if matches(row)]
        if self.maximum is not None:
            rows = rows[: self.maximum]
        if self.selected_columns is not None:
            projected = []
            for r in rows:
                projected.append({col: r.get(col) for col in self.selected_columns})
            rows = projected
        return SimpleNamespace(data=rows)


class MockSupabaseClient:
    def __init__(self, state, auth_user_id=None, role=None):
        self.state = state
        self.call_log = []
        self.auth_user_id = auth_user_id
        self.role = role

    def table(self, name):
        return Query(self.state, name)

    def rpc(self, name, params):
        self.call_log.append({"op": "rpc", "fn": name, "params": params})

        def execute():
            session = next(
                (
                    s
                    for s in self.state.get("exam_sessions", [])
                    if s.get("id") == params.get("p_session_id")
                ),
                None,
            )
            if name == "finalize_approve_session" and session:
                if self.role == "authenticated" and self.auth_user_id != session.get("user_id"):
                    raise RuntimeError("ERR_UNAUTHORIZED")
                if session.get("status") != "reviewed":
                    raise RuntimeError("ERR_INVALID_SESSION_STATE")
                timestamp = datetime.now(timezone.utc).isoformat()
                session.update(status="approved", approved_at=timestamp, updated_at=timestamp)
                self.state.setdefault("review_logs", []).append({"action_type": "APPROVE_ALL"})
                return SimpleNamespace(
                    data={
                        "session_id": session["id"],
                        "status": "approved",
                        "approved_at": timestamp,
                        "updated_at": timestamp,
                    }
                )
            if (
                name
                in {
                    "review_accept_question",
                    "review_revert_question",
                    "review_reserve_regeneration",
                }
                and session
                and session.get("status") in {"approved", "exported"}
            ):
                raise RuntimeError("REVIEW_LOCKED")
            raise RuntimeError(f"RPC {name} requires an explicit test stub")

        return SimpleNamespace(execute=execute)
