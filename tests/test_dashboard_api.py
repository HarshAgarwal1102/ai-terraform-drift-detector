"""Tests for the dashboard data API (Task 13.1).

Run from the repository root:
    pytest tests/test_dashboard_api.py

Two kinds of data:
- the real public artifacts of the Task 9B.6 cycle 2 runs (R2 #38, R3 #39, R4 #40),
  copied unchanged into tests/fixtures/dashboard/real_9b6;
- synthetic runs built by the real pipeline (plan -> public drift report ->
  investigation -> public investigation) with a fake Activity Log source, so the
  `Caller recorded by Azure` lookup runs exactly as in `drift-engine who`. Their
  callers are sentinels that must never reach a log, a file or an unauthorized response.

No Azure, network or credentials.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import logging
import os
import secrets
import sys
import threading
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TESTS)

from test_activity_logs import NSG_ADDR, NSG_ID, RG, RG_ADDR, RG_ID, FakeSource, al, page  # noqa: E402
from test_investigation import at_time, nsg_drift, public_report_bytes  # noqa: E402
from test_who import NOW, _WhoBase, state_json  # noqa: E402

try:
    from fastapi.testclient import TestClient

    from dashboard_api import auth, cli, store
    from dashboard_api.app import create_app
    from drift_engine import investigation as inv
    from drift_engine import investigation_public as pub
    from drift_engine import who
except ImportError:  # the dashboard extra (or httpx) is not installed
    TestClient = None

REAL = os.path.join(TESTS, "fixtures", "dashboard", "real_9b6")
REAL_R2, REAL_R3, REAL_R4 = "github-38105671846-1", "github-38109121618-1", "github-38111406531-1"
RUN = "github-500-1"
HUMAN = "sentinel.human.7f3a@example.com"
SP_ID = "5e171ce1-0000-4000-8000-00000000a5b1"
MI_ID = "5e171ce1-0000-4000-8000-00000000b4c2"
SENTINELS = (HUMAN, SP_ID, MI_ID, "sentinel-")
CLAIMS = {
    "user": {"idtyp": "user"},
    "service_principal": {"idtyp": "app", "appid": "5e171ce1-0000-4000-8000-0000000a991d"},
    "managed_identity": {"idtyp": "app", "appid": "5e171ce1-0000-4000-8000-0000000a991e",
                         "xms_mirid": f"{RG_ID}/providers/Microsoft.ManagedIdentity/userAssignedIdentities/x"},
}


class _Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.text: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.text.append(f"{record.name} {record.getMessage()} {getattr(record, 'event', '')} "
                         f"{json.dumps(getattr(record, 'fields', {}), default=str)} {record.exc_text or ''}")


@unittest.skipIf(TestClient is None, "dashboard extra not installed (pip install -e '.[dashboard]')")
class _DashboardBase(_WhoBase):
    def setUp(self) -> None:
        super().setUp()
        self.tokens = {}
        self.users_file = os.path.join(self.tmp, "users.json")
        self.write_users({"maintainer": ["viewer", "caller_reader"], "viewer": ["viewer"], "nobody": []})
        root = logging.getLogger()
        self.capture, self.old_level = _Capture(), root.level
        root.addHandler(self.capture)
        root.setLevel(logging.DEBUG)
        self.addCleanup(root.removeHandler, self.capture)
        self.addCleanup(root.setLevel, self.old_level)

    def write_users(self, roles: dict[str, list[str]], mode: int = 0o600) -> None:
        users = []
        for name, granted in roles.items():
            self.tokens.setdefault(name, secrets.token_urlsafe(32))
            users.append({"name": name, "token_sha256": auth.token_digest(self.tokens[name]), "roles": granted})
        with open(self.users_file, "w", encoding="utf-8") as fh:
            json.dump({"users": users}, fh)
        os.chmod(self.users_file, mode)

    def headers(self, user: str = "maintainer") -> dict:
        return {"Authorization": f"Bearer {self.tokens[user]}"}

    def client(self, data_dir: str, *, rows=None, source=None, terraform: bytes | None = b"default", now=NOW,
               environ=None) -> "TestClient":
        terraform_path = None
        if terraform is not None:
            terraform_path = os.path.join(self.dir("terraform"), "state.json")
            with open(terraform_path, "wb") as fh:
                fh.write(state_json({NSG_ADDR: NSG_ID}) if terraform == b"default" else terraform)
        source = source if source is not None else FakeSource({RG: [page(*(rows or []))]})
        return TestClient(create_app(data_dir=data_dir, users_file=self.users_file, terraform_json=terraform_path,
                                     source=source, now=lambda: now, environ={} if environ is None else environ))

    # -- synthetic runs built by the real pipeline -----------------------------------------------------

    def run_dir(self, rows, *, investigation=True, ai=True) -> str:
        entries = nsg_drift()
        paths = self.plan(entries)
        report = public_report_bytes(paths)  # the drift-report artifact; investigate reads the internal report
        result = self.inv_run(entries, rows, paths=paths)
        text, problems = inv.publish(result.document)
        self.assertEqual(problems, [])
        data = self.dir("data")
        self.put(data, "drift-report-500", "drift_report.json", report)
        if investigation:
            self.put(data, "drift-investigation-500", "drift_investigation.json", text.encode())
        if ai:
            self.put(data, "ai-analysis-report-500", "ai_analysis_report.json",
                     json.dumps(self.ai_report(report, text.encode())).encode())
        return data

    @staticmethod
    def put(data: str, artifact: str, name: str, content: bytes) -> str:
        os.makedirs(os.path.join(data, artifact), exist_ok=True)
        path = os.path.join(data, artifact, name)
        with open(path, "wb") as fh:
            fh.write(content)
        return path

    @staticmethod
    def ai_report(report: bytes, investigation: bytes | None) -> dict:
        """The fields of an AI report v2 that the API reads, bound to `report`."""
        option = f"{NSG_ADDR}#1"
        return {
            "report_version": "2",
            "provenance": {"run_id": RUN, "drift_report_sha256": pub.canonical_sha256(json.loads(report)),
                           "investigation_sha256": None if investigation is None
                           else pub.canonical_sha256(json.loads(investigation))},
            "analysis": {"security": {"status": "complete", "findings": [{"basis": "inference"}]}},
            "remediation": {"approval_required": True, "automatic_apply": False, "options": [{
                "address": NSG_ADDR, "option_id": option, "kind": "restore_declared", "direction": "apply_plan",
                "description": "Apply the reviewed plan.", "destructive": False, "terraform_plan_action": "update",
                "approval": {"approver": None, "decided_at": None, "destructive_confirmation_required": False,
                             "required": True, "status": "pending"},
                "execution": {"allowed": False, "automatic_apply": False, "mode": "manual_after_approval"}}]},
            "resources": [{"address": NSG_ADDR, "analysis": {"narrative": [{"id": "n", "text": "narrative"}]},
                           "remediation": {"recommendation": {
                               "decision": "recommended", "kind": "restore_declared", "option_id": option,
                               "policy_rule": "R4", "approval_required": True, "automatic_apply": False,
                               "execution_allowed": False}}}],
        }

    @staticmethod
    def tagged(caller: str | None, kind: str = "user", hour: int = 8, log=None) -> list[dict]:
        rows = log.tags(at_time(hour), caller=caller)
        return [dict(r, claims=CLAIMS[kind]) for r in rows]

    def caller(self, response) -> dict:
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers["cache-control"], "no-store")
        drifts = response.json()["drifts"]
        self.assertEqual(len(drifts), 1)
        return drifts[0]["caller_recorded_by_azure"]

    def files(self, root: str) -> dict:
        out = {}
        for directory, _, names in os.walk(root):
            for name in names:
                path = os.path.join(directory, name)
                with open(path, "rb") as fh:
                    out[path] = fh.read()
        return out

    def assert_no_sentinel(self, text: str) -> None:
        for sentinel in SENTINELS:
            self.assertNotIn(sentinel, text)


class CallerTests(_DashboardBase):
    def test_recorded_caller_for_each_caller_type(self):
        for kind, recorded in (("user", HUMAN), ("service_principal", SP_ID), ("managed_identity", MI_ID)):
            with self.subTest(kind):
                rows = self.tagged(recorded, kind, log=self.log)
                client = self.client(self.run_dir(rows), rows=rows)
                for url in ("/api/drifts?include_caller=true", f"/api/reports/{RUN}?include_caller=true"):
                    result = self.caller(client.get(url, headers=self.headers()))
                    self.assertEqual(result, {"label": "Caller recorded by Azure", "value": recorded,
                                              "caller_type": kind, "status": "matched"})

    def test_unknown_cases(self):
        rows = self.tagged(HUMAN, log=self.log)
        twin = [dict(r, eventDataId=r["eventDataId"].replace("9000", "9100"), correlationId="corr-twin")
                for r in rows]
        inconsistent = [rows[0], dict(rows[1], caller="sentinel-other@example.com")]
        missing = self.tagged(None, log=self.log)
        cases = {
            "no_investigation": dict(data=dict(rows=rows, investigation=False), rows=rows),
            "no_decisive_operation": dict(data=dict(rows=[]), rows=rows),
            "caller_missing": dict(data=dict(rows=missing), rows=missing),
            "caller_inconsistent": dict(data=dict(rows=inconsistent), rows=inconsistent),
            "no_match": dict(data=dict(rows=rows), rows=[]),
            "multiple_matches": dict(data=dict(rows=rows), rows=rows + twin),
            "retention_exceeded": dict(data=dict(rows=rows), rows=rows, now=at_time(8) + dt.timedelta(days=91)),
            "query_failed": dict(data=dict(rows=rows), source=FakeSource({RG: [al.SourceError("throttled", 429)]})),
            "azure_sign_in_unavailable": dict(data=dict(rows=rows),
                                              source=FakeSource({RG: [al.SourceError("credential_unavailable")]})),
            "azure_access_denied": dict(data=dict(rows=rows),
                                        source=FakeSource({RG: [al.SourceError("authorization_failed", 403)]})),
            "address_unknown": dict(data=dict(rows=rows), rows=rows, terraform=state_json({RG_ADDR: RG_ID})),
            "invalid_resource_id": dict(data=dict(rows=rows), rows=rows,
                                        terraform=state_json({NSG_ADDR: "/not/an/id"})),
            "resource_ids_unavailable": dict(data=dict(rows=rows), rows=rows, terraform=None),
            "local_only": dict(data=dict(rows=rows), rows=rows, environ={"GITHUB_ACTIONS": "true"}),
        }
        for status, kwargs in cases.items():
            with self.subTest(status):
                data = self.run_dir(**kwargs.pop("data"))
                result = self.caller(self.client(data, **kwargs).get("/api/drifts?include_caller=true",
                                                                     headers=self.headers()))
                self.assertEqual((result["value"], result["status"]), ("Unknown", status))
                self.assert_no_sentinel(json.dumps(result))

    def test_rejected_azure_sign_in_is_unknown_with_its_reason(self):
        rows = self.tagged(HUMAN, log=self.log)
        source = FakeSource({RG: [al.SourceError("authentication_failed", 401)]})
        result = self.caller(self.client(self.run_dir(rows), source=source)
                             .get("/api/drifts?include_caller=true", headers=self.headers()))
        self.assertEqual((result["value"], result["status"]), ("Unknown", "azure_sign_in_unavailable"))

    def test_unsettled_evidence_is_never_looked_up(self):
        """G8: an investigation whose Activity Log evidence had not settled yields Unknown, with no query."""
        rows = self.tagged(HUMAN, log=self.log)
        data = self.run_dir(rows)
        path = os.path.join(data, "drift-investigation-500", "drift_investigation.json")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        self.assertEqual(text.count('"settled": true'), 1)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text.replace('"settled": true', '"settled": false'))
        source = FakeSource({RG: [page(*rows)]})
        result = self.caller(self.client(data, source=source).get("/api/drifts?include_caller=true",
                                                                  headers=self.headers()))
        self.assertEqual((result["value"], result["status"]), ("Unknown", "activity_log_not_settled"))
        self.assertEqual(source.calls, [])

    def test_unreadable_terraform_json_is_unknown(self):
        rows = self.tagged(HUMAN, log=self.log)
        result = self.caller(self.client(self.run_dir(rows), rows=rows, terraform=b"not json")
                             .get("/api/drifts?include_caller=true", headers=self.headers()))
        self.assertEqual((result["value"], result["status"]), ("Unknown", "resource_ids_unavailable"))

    def test_without_include_caller_azure_is_never_queried(self):
        rows = self.tagged(HUMAN, log=self.log)
        source = FakeSource({RG: [page(*rows)]})
        client = self.client(self.run_dir(rows), source=source)
        response = client.get("/api/drifts", headers=self.headers())
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("caller_recorded_by_azure", response.json()["drifts"][0])
        self.assertEqual(source.calls, [])
        self.assert_no_sentinel(response.text)


class AmbiguousVerdictCallerTests(_DashboardBase):
    """Regression: `github-38109121618-1` (R3, Control A) has verdict `ambiguous` with two capable tag writes
    (`op-1` R2's, `op-2` R3's). `drift-engine who` matched a caller for each; the dashboard returned only
    `Unknown` (`no_decisive_operation`) without looking either up. The real public artifacts are used
    unchanged; the Activity Log rows reproduce the two real operations to the microsecond."""

    OPS = (("2026-10-11T02:27:00.310062Z", "2026-10-11T02:27:03.028847Z"),
           ("2026-10-11T03:34:30.341314Z", "2026-10-11T03:34:32.794486Z"))
    PORTAL_USER = {"idtyp": "user", "appid": "c44b4083-3bb0-49c1-b47d-974e53cbdf3c"}
    OP2_CALLER = "sentinel-r3-op2@example.com"
    NOW = dt.datetime(2026, 10, 17, 6, 0, tzinfo=dt.timezone.utc)

    def rows(self) -> list[dict]:
        out = []
        for (start, end), caller in zip(self.OPS, (HUMAN, self.OP2_CALLER)):
            begin, done = self.log.tags(at_time(0), rid=RG_ID, caller=caller)
            out += [dict(begin, eventTimestamp=start, submissionTimestamp=start, claims=self.PORTAL_USER),
                    dict(done, eventTimestamp=end, submissionTimestamp=end, claims=self.PORTAL_USER)]
        return out

    def get(self, *, rows=None, source=None, terraform=b"r3", now=None, environ=None, user="maintainer"):
        terraform = state_json({RG_ADDR: RG_ID}) if terraform == b"r3" else terraform
        source = source if source is not None else FakeSource({RG: [page(*(self.rows() if rows is None else rows))]})
        client = self.client(REAL, source=source, terraform=terraform, now=now or self.NOW, environ=environ)
        return client, client.get(f"/api/reports/{REAL_R3}?include_caller=true", headers=self.headers(user))

    def test_each_operation_has_the_caller_drift_engine_who_finds(self):
        client, response = self.get()
        result = self.caller(response)
        self.assertEqual((result["value"], result["status"]), ("Unknown", "no_decisive_operation"))  # no single caller
        self.assertEqual([(o["op_id"], o["start"], o["end"], o["role"], o["status"], o["caller_type"], o["value"])
                          for o in result["operations"]],
                         [("op-1", *self.OPS[0], "capable", "matched", "user", HUMAN),
                          ("op-2", *self.OPS[1], "capable", "matched", "user", self.OP2_CALLER)])
        drifts = client.get(f"/api/drifts?report_id={REAL_R3}&include_caller=true", headers=self.headers()).json()
        self.assertEqual(drifts["drifts"][0]["caller_recorded_by_azure"], result)

        # the CLI path on the same inputs: `drift-engine who --public --report --terraform`
        with open(os.path.join(REAL, "drift-investigation-38109121618", "drift_investigation.json"), "rb") as fh:
            public = fh.read()
        with open(os.path.join(REAL, "drift-report-38109121618", "drift_report.json"), "rb") as fh:
            report = fh.read()
        cli = who.run_who(public, state_json({RG_ADDR: RG_ID}), source=FakeSource({RG: [page(*self.rows())]}),
                          now=self.NOW, report_bytes=report, environ={})
        self.assertTrue(cli.complete)
        self.assertEqual([(r["op_id"], r["status"], r["callers"]) for r in cli.document["results"]],
                         [(o["op_id"], o["status"], [o["value"]]) for o in result["operations"]])
        self.assertFalse(any(self.OP2_CALLER in line or HUMAN in line for line in self.capture.text))

    def test_unavailable_evidence_stays_unknown_per_operation(self):
        rows = self.rows()
        cases = {
            "no_match": dict(rows=[]),
            "retention_exceeded": dict(now=self.NOW + dt.timedelta(days=90)),
            "resource_ids_unavailable": dict(terraform=None),
            "address_unknown": dict(terraform=state_json({NSG_ADDR: NSG_ID})),
            "azure_sign_in_unavailable": dict(source=FakeSource({RG: [al.SourceError("credential_unavailable")]})),
            "local_only": dict(environ={"GITHUB_ACTIONS": "true"}, source=FakeSource({RG: [page(*rows)]})),
        }
        for status, kwargs in cases.items():
            with self.subTest(status):
                source = kwargs.get("source")
                result = self.caller(self.get(**kwargs)[1])
                self.assertEqual((result["value"], result["status"]), ("Unknown", "no_decisive_operation"))
                self.assertEqual([(o["op_id"], o["value"], o["status"]) for o in result["operations"]],
                                 [("op-1", "Unknown", status), ("op-2", "Unknown", status)])
                self.assert_no_sentinel(json.dumps(result))
                if status == "local_only":
                    self.assertEqual(source.calls, [])

    def test_operation_lookups_run_concurrently(self):
        """Run History performance: the two Activity Log queries of R3 overlap instead of running one after the
        other (each takes about a second on real Azure). The source only answers once both have started."""
        inner = FakeSource({RG: [page(*self.rows())]})
        barrier = threading.Barrier(2, timeout=5)

        class BothAtOnce:
            calls = inner.calls

            def pages(self, subscription_id, query_filter):
                barrier.wait()  # raises BrokenBarrierError (then: query_failed) if the queries run sequentially
                yield from inner.pages(subscription_id, query_filter)

        result = self.caller(self.get(source=BothAtOnce())[1])
        self.assertEqual([(o["op_id"], o["status"], o["value"]) for o in result["operations"]],
                         [("op-1", "matched", HUMAN), ("op-2", "matched", self.OP2_CALLER)])  # order kept
        self.assertEqual(len(inner.calls), 2)

    def test_viewer_never_receives_the_operation_callers(self):
        source = FakeSource({RG: [page(*self.rows())]})
        client, response = self.get(source=source, user="viewer")
        self.assertEqual((response.status_code, response.json()), (403, {"error": "caller_access_denied"}))
        plain = client.get(f"/api/reports/{REAL_R3}", headers=self.headers("viewer"))
        self.assertNotIn("caller_recorded_by_azure", plain.json()["drifts"][0])
        self.assertEqual(source.calls, [])
        self.assert_no_sentinel(plain.text)


class AccessTests(_DashboardBase):
    def setUp(self) -> None:
        super().setUp()
        self.rows = self.tagged(HUMAN, log=self.log)
        self.data = self.run_dir(self.rows)

    def test_unauthenticated_requests_are_refused(self):
        client = self.client(self.data, rows=self.rows)
        for headers in ({}, {"Authorization": "Bearer wrong-token"}, {"Authorization": self.tokens["maintainer"]},
                        {"Authorization": f"Basic {self.tokens['maintainer']}"}, {"Authorization": "Bearer "}):
            for url in ("/api/summary", "/api/drifts?include_caller=true", f"/api/reports/{RUN}?include_caller=true",
                        "/api/remediations"):
                with self.subTest(headers=list(headers.values()), url=url):
                    response = client.get(url, headers=headers)
                    self.assertEqual((response.status_code, response.json()), (401, {"error": "unauthenticated"}))
                    self.assertEqual(response.headers["www-authenticate"], "Bearer")
                    self.assertEqual(response.headers["cache-control"], "no-store")
                    self.assert_no_sentinel(response.text)

    def test_unauthorized_requests_are_refused(self):
        source = FakeSource({RG: [page(*self.rows)]})
        client = self.client(self.data, source=source)
        for url in ("/api/drifts?include_caller=true", f"/api/reports/{RUN}?include_caller=true"):
            with self.subTest(url):
                response = client.get(url, headers=self.headers("viewer"))
                self.assertEqual((response.status_code, response.json()), (403, {"error": "caller_access_denied"}))
                self.assert_no_sentinel(response.text)
        for url in ("/api/summary", "/api/drifts"):
            with self.subTest(url):
                response = client.get(url, headers=self.headers("nobody"))
                self.assertEqual((response.status_code, response.json()), (403, {"error": "forbidden"}))
        self.assertEqual(client.get("/api/drifts", headers=self.headers("viewer")).status_code, 200)
        self.assertEqual(source.calls, [])  # no refused request reached Azure

    def test_unusable_users_file_fails_closed(self):
        client = self.client(self.data, rows=self.rows)
        cases = {
            "group_writable": lambda: os.chmod(self.users_file, 0o620),
            "invalid": lambda: open(self.users_file, "w").write('{"users": [{"name": "x"}]}'),
            "duplicate_digest": lambda: open(self.users_file, "w").write(json.dumps({"users": [
                {"name": n, "token_sha256": "0" * 64, "roles": ["viewer"]} for n in ("a", "b")]})),
            "unknown_role": lambda: open(self.users_file, "w").write(json.dumps({"users": [
                {"name": "a", "token_sha256": "0" * 64, "roles": ["admin"]}]})),
            "missing": lambda: os.remove(self.users_file),
        }
        for name, damage in cases.items():
            with self.subTest(name):
                self.write_users({"maintainer": ["viewer", "caller_reader"]})
                damage()
                response = client.get("/api/drifts?include_caller=true", headers=self.headers())
                self.assertEqual((response.status_code, response.json()), (503, {"error": "auth_unavailable"}))

    def test_removed_user_loses_access_at_once(self):
        client = self.client(self.data, rows=self.rows)
        self.assertEqual(client.get("/api/summary", headers=self.headers("viewer")).status_code, 200)
        self.write_users({"maintainer": ["viewer", "caller_reader"]})
        self.assertEqual(client.get("/api/summary", headers=self.headers("viewer")).status_code, 401)

    def test_authenticate_is_exact(self):
        users = auth.load_users(self.users_file)
        self.assertEqual(auth.authenticate(f"Bearer {self.tokens['viewer']}", users).name, "viewer")
        self.assertEqual(auth.authenticate(f"bearer  {self.tokens['viewer']} ", users).name, "viewer")
        for header in (None, "", "Bearer", f"Bearer {self.tokens['viewer']}x", f"Token {self.tokens['viewer']}"):
            self.assertIsNone(auth.authenticate(header, users))


class NoPersistenceTests(_DashboardBase):
    def test_caller_identity_is_never_stored_or_logged(self):
        rows = self.tagged(HUMAN, log=self.log)
        data = self.run_dir(rows)
        before, cwd_before = self.files(self.tmp), sorted(os.listdir(os.getcwd()))
        client = self.client(data, rows=rows)
        for _ in range(2):
            response = client.get("/api/drifts?include_caller=true", headers=self.headers())
            self.assertEqual(self.caller(response)["value"], HUMAN)
            self.assertEqual(self.caller(client.get(f"/api/reports/{RUN}?include_caller=true",
                                                    headers=self.headers()))["value"], HUMAN)
        for url in ("/api/summary", "/api/drifts", f"/api/reports/{RUN}", "/api/remediations"):
            self.assert_no_sentinel(client.get(url, headers=self.headers()).text)
        after = self.files(self.tmp)
        self.assertEqual({p: c for p, c in after.items() if "terraform-" not in p},
                         {p: c for p, c in before.items() if "terraform-" not in p})  # nothing new, nothing changed
        self.assertEqual(sorted(os.listdir(os.getcwd())), cwd_before)
        self.assertFalse(any(name.endswith("who_evidence.local.json") for name in after))
        self.assertTrue(any("dashboard_caller_lookup" in line for line in self.capture.text))
        self.assert_no_sentinel("\n".join(self.capture.text))


class EndpointTests(_DashboardBase):
    def test_real_artifacts(self):
        client = self.client(REAL, terraform=None)
        summary = client.get("/api/summary", headers=self.headers()).json()
        self.assertEqual((summary["reports_total"], summary["data_problems"]), (3, {}))
        self.assertEqual([h["report_id"] for h in summary["history"]], [REAL_R4, REAL_R3, REAL_R2])
        self.assertEqual({(h["drifted_resources"], h["resources_total"]) for h in summary["history"]}, {(0, 5), (1, 5)})
        self.assertEqual(summary["history"][0]["unmanaged"], {"available": False, "unmanaged": None, "display": None,
                                                              "cost_status": "not_in_ai_report"})
        latest = summary["environments"][0]
        self.assertEqual((latest["report_id"], latest["environment"], latest["drifted_resources"]), (REAL_R4, "dev", 0))
        self.assertEqual(latest["artifacts"], {"ai_analysis_report": True, "investigation": True, "cost_run": True,
                                               "unmanaged_inventory": False})  # 9B.6 predates Task 10.4
        self.assertEqual((latest["unmanaged"]["available"], latest["unmanaged"]["cost_status"]),
                         (False, "not_in_ai_report"))
        self.assertEqual(summary["overview"]["total_resources"], 5)
        self.assertEqual(summary["overview"]["monthly_cost_impact"]["complete"], False)  # not estimated by the API

        drifts = client.get(f"/api/drifts?report_id={REAL_R2}", headers=self.headers()).json()["drifts"]
        self.assertEqual(len(drifts), 1)
        drift = drifts[0]
        self.assertEqual((drift["address"], drift["severity"], drift["classification"]),
                         ('module.resource_group.azurerm_resource_group.this["main"]', "LOW", "external_drift"))
        self.assertEqual(drift["changes"][0]["property"], "tags.drift_test")
        self.assertEqual((drift["changes"][0]["expected"], drift["changes"][0]["actual"]),
                         ({"status": "absent"}, {"status": "value", "value": "primary-r2"}))
        self.assertEqual((drift["operation"]["op_id"], drift["operation"]["operation_name"], drift["operation"]["start"]),
                         ("op-1", "Microsoft.Resources/tags/write", "2026-10-11T02:27:00.310062Z"))
        self.assertEqual(drift["remediation"]["decision"], "recommended")
        self.assertTrue(drift["ai_analysis"]["available"])

        report = client.get(f"/api/reports/{REAL_R2}?include_caller=true", headers=self.headers()).json()
        self.assertEqual(report["artifacts"]["investigation"]["exposure"]["caller_identity"], "withheld")
        self.assertEqual(report["drifts"][0]["caller_recorded_by_azure"]["value"], "Unknown")  # no state file here
        remediations = client.get(f"/api/remediations?report_id={REAL_R2}", headers=self.headers()).json()
        self.assertEqual((remediations["count"], remediations["pending_approvals"]), (2, 2))
        self.assertEqual([(o["kind"], o["recommended"], o["policy_rule"]) for o in remediations["remediations"]],
                         [("restore_declared", True, "R4"), ("accept_remote_value", False, None)])
        self.assertEqual({o["execution"]["allowed"] for o in remediations["remediations"]}, {False})
        self.assertNotIn("approver", remediations["remediations"][0]["approval"])

    def test_filters_and_not_found(self):
        rows = self.tagged(HUMAN, log=self.log)
        client = self.client(self.run_dir(rows), rows=rows)
        get = lambda url: client.get(url, headers=self.headers())  # noqa: E731
        self.assertEqual(get("/api/drifts?severity=info").json()["count"], 0)
        self.assertEqual(get("/api/drifts?environment=prod").json()["count"], 0)
        self.assertEqual(get("/api/drifts?environment=dev&resource_type=azurerm_network_security_group")
                         .json()["count"], 1)
        severity = get("/api/drifts").json()["drifts"][0]["severity"]
        self.assertEqual(get(f"/api/drifts?severity={severity.lower()}").json()["count"], 1)
        for url in ("/api/reports/github-1-1", "/api/reports/.hidden", "/api/drifts?report_id=nope"):
            with self.subTest(url):
                self.assertEqual((get(url).status_code, get(url).json()), (404, {"error": "report_not_found"}))
        self.assertEqual(get("/api/reports/..%2F..%2Fetc").json(), {"error": "not_found"})
        invalid = get(f"/api/drifts?include_caller=sentinel-{HUMAN}")  # validation errors never echo input
        self.assertEqual((invalid.status_code, invalid.json()), (422, {"error": "invalid_request"}))
        summary = get("/api/summary").json()
        self.assertEqual(summary["overview"]["active_drifts"], 1)
        self.assertEqual(summary["environments"][0]["security_exposure"]["ai_security_findings"], 1)
        self.assertEqual(get("/api/remediations").json()["remediations"][0]["recommended"], True)

    def test_missing_data_directory(self):
        client = self.client(os.path.join(self.tmp, "absent"))
        response = client.get("/api/summary", headers=self.headers())
        self.assertEqual((response.status_code, response.json()), (503, {"error": "data_unavailable"}))
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_no_api_docs(self):
        client = self.client(REAL, terraform=None)
        for url in ("/docs", "/redoc", "/openapi.json"):
            self.assertEqual(client.get(url).status_code, 404)


class StoreTests(_DashboardBase):
    def setUp(self) -> None:
        super().setUp()
        self.rows = self.tagged(HUMAN, log=self.log)
        self.data = self.run_dir(self.rows)

    def read(self, *parts) -> bytes:
        with open(os.path.join(self.data, *parts), "rb") as fh:
            return fh.read()

    def test_bound_artifacts_are_attached(self):
        bundle = store.load(self.data).get(RUN)
        self.assertIsNotNone(bundle.ai_report)
        self.assertIsNotNone(bundle.investigation)
        self.assertEqual(bundle.problems, ())

    def test_unbound_and_ambiguous_artifacts_are_not_used(self):
        report = json.loads(self.read("drift-report-500", "drift_report.json"))
        ai = json.loads(self.read("ai-analysis-report-500", "ai_analysis_report.json"))
        other = copy.deepcopy(ai)
        other["provenance"]["drift_report_sha256"] = "0" * 64
        self.put(self.data, "x-unbound", "ai_analysis_report.json", json.dumps(other).encode())
        self.assertIsNotNone(store.load(self.data).get(RUN).ai_report)  # an unbound AI report is ignored
        twin = copy.deepcopy(ai)
        twin["limitations"] = ["different"]
        self.put(self.data, "x-twin", "ai_analysis_report.json", json.dumps(twin).encode())
        bundle = store.load(self.data).get(RUN)
        self.assertIsNone(bundle.ai_report)
        self.assertIn("ai_report_ambiguous", bundle.problems)
        conflict = dict(report, has_drift=not report["has_drift"])
        self.put(self.data, "x-conflict", "drift_report.json", json.dumps(conflict).encode())
        index = store.load(self.data)
        self.assertIsNone(index.get(RUN))  # two different reports for one run: neither is used
        self.assertEqual(index.problems["report_conflict"], 1)

    def test_leaking_or_invalid_files_are_skipped(self):
        public = self.read("drift-investigation-500", "drift_investigation.json")
        self.put(self.data, "x-leak", "drift_investigation.json", public.replace(b'"github-500-1"', b'"a@b.example"'))
        self.put(self.data, "x-bad", "drift_report.json", b"{")
        self.put(self.data, "x-nan", "drift_report.json", b'{"run": NaN}')
        index = store.load(self.data)
        self.assertEqual((index.problems["investigation_leak"], index.problems["report_invalid"]), (1, 2))
        self.assertIsNotNone(index.get(RUN).investigation)

    def test_hidden_staging_folders_are_never_indexed(self):
        """Task 13.4: a fetch writes into a hidden `.fetch-*` folder before renaming it into place."""
        report = json.loads(self.read("drift-report-500", "drift_report.json"))
        other = dict(report, run=dict(report["run"], run_id="github-501-1"))
        self.put(self.data, ".fetch-abc123", "drift_report.json", json.dumps(other).encode())
        self.put(self.data, ".hidden", "drift_report.json", json.dumps(other).encode())
        index = store.load(self.data)
        self.assertIsNone(index.get("github-501-1"))
        self.assertIsNotNone(index.get(RUN))
        self.assertEqual(index.problems, {})

    def test_drift_reports_must_validate_as_the_public_report(self):
        """Task 13.4 hardening: the right shape is not enough; the public drift report model must accept it."""
        report = json.loads(self.read("drift-report-500", "drift_report.json"))
        for name, broken in (("x-extra", dict(report, run=dict(report["run"], run_id="github-502-1"), unexpected=1)),
                             ("x-internal", {k: v for k, v in dict(report, run=dict(report["run"], run_id="github-503-1"))
                                             .items() if k != "public_version"})):
            self.put(self.data, name, "drift_report.json", json.dumps(broken).encode())
        index = store.load(self.data)
        self.assertIsNone(index.get("github-502-1"))
        self.assertIsNone(index.get("github-503-1"))
        self.assertEqual(index.problems["report_invalid"], 2)
        self.assertIsNotNone(index.get(RUN))

    def test_symbolic_links_are_not_followed(self):
        outside = self.dir("outside")
        os.rename(os.path.join(self.data, "drift-report-500"), os.path.join(outside, "drift-report-500"))
        os.symlink(os.path.join(outside, "drift-report-500"), os.path.join(self.data, "linked"))
        self.assertEqual(store.load(self.data).bundles, [])
        link = os.path.join(self.dir("linkdata"), "data")
        os.symlink(self.data, link)
        with self.assertRaises(store.StoreUnavailable):
            store.load(link)


@unittest.skipIf(TestClient is None, "dashboard extra not installed (pip install -e '.[dashboard]')")
class CliTests(unittest.TestCase):
    def test_loopback_only(self):
        for host in ("127.0.0.1", "::1", "localhost", "127.0.0.2"):
            self.assertTrue(cli.is_loopback(host), host)
        for host in ("0.0.0.0", "::", "192.168.1.10", "example.com"):
            self.assertFalse(cli.is_loopback(host), host)
        import contextlib
        import io
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(["--host", "0.0.0.0"]), 2)


if __name__ == "__main__":
    unittest.main()
