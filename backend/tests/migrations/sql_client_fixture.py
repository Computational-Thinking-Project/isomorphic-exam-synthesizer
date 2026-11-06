"""Minimal PostgREST wire substitute; all data and RPC execution use PostgreSQL.

JWT validation is injected by tests. Table queries use the fixture DB superuser;
RPCs run with actual owner/worker roles, so RPC ACL/ownership is real.
"""

import json
from types import SimpleNamespace

from test_review_rpcs import OWNER, ReviewRpcTests, literal


class SqlClient:
    def __init__(self, case, worker=False):
        self.case, self.worker, self.calls = case, worker, []

    def rpc(self, name, params):
        self.calls.append((name, params))

        def execute():
            arguments = ",".join(
                f"{k}=>{literal(json.dumps(v) if isinstance(v, (list, dict)) else v)}"
                for k, v in params.items()
            )
            result = self.case.sql(
                ReviewRpcTests.auth("service_role" if self.worker else "authenticated", OWNER)
                + f"SELECT public.{name}({arguments});"
            )
            return SimpleNamespace(data=json.loads(result.stdout))

        return SimpleNamespace(execute=execute)

    def table(self, name):
        case = self.case

        class Query:
            def __init__(self):
                self.filters = []

            def select(self, columns):
                return self

            def eq(self, column, value):
                if column == "exam_versions.session_id":
                    self.filters.append(
                        f"q.version_id IN (SELECT id FROM exam_versions WHERE session_id={literal(value)})"
                    )
                else:
                    self.filters.append(f"q.{column}={literal(value)}")
                return self

            def order(self, *args, **kwargs):
                return self

            def limit(self, *args):
                return self

            def execute(self):
                where = " AND ".join(self.filters) or "true"
                value = case.value(
                    f"SELECT coalesce(jsonb_agg(to_jsonb(q)),'[]'::jsonb) FROM public.{name} q WHERE {where};"
                )
                return SimpleNamespace(data=json.loads(value))

        return Query()
