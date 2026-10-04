"""Tests for the local WHO path and the bounded-window collector (Task 9B.3).

Run from the repository root:
    pytest tests/test_who.py

No Azure, network or credentials: the investigation that produces the public file and
`drift-engine who` both read a fake Activity Log source. Callers, IDs and addresses
are synthetic.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import io
import json
import os
import stat
import sys
import unittest
from unittest import mock

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TESTS)

from test_activity_logs import (  # noqa: E402  (shared helpers; no test classes imported)
    CALLER, NSG_ADDR, NSG_ID, RG, RG_ADDR, RG_ID, SUB, FakeSource, NoCallSource, al, ev, page,
)
from test_investigation import (  # noqa: E402
    REPO, TAGS_OP, UTC, FakeClock, _Base, at_time, nsg_drift, report_bytes,
)

try:
    from drift_engine import cli
    from drift_engine import investigation as inv
    from drift_engine import investigation_public as pub
    from drift_engine import who
except ImportError:  # pydantic not installed
    who = None

NOW = dt.datetime(2026, 10, 4, 9, 0, tzinfo=UTC)
NO_CI = {k: v for k, v in os.environ.items() if k != "GITHUB_ACTIONS"}


def state_json(ids: dict[str, str], nested: bool = True) -> bytes:
    """`terraform show -json` state with the resources in a child module."""
    resources = [{"address": a, "mode": "managed", "type": "x", "name": "this", "values": {"id": i}}
                 for a, i in ids.items()]
    root = {"resources": [{"address": "data.x.y", "mode": "data", "values": {"id": "ignored"}}],
            "child_modules": [{"address": "module.m", "resources": resources}]} if nested else {"resources": resources}
    return json.dumps({"format_version": "1.0", "values": {"root_module": root}}).encode()


def plan_json(ids: dict[str, str]) -> bytes:
    return json.dumps({"format_version": "1.2", "prior_state": json.loads(state_json(ids))}).encode()


def shift(rows: list[dict], **delta) -> list[dict]:
    out = []
    for row in rows:
        moment = al.parse_timestamp(row["eventTimestamp"]) + dt.timedelta(**delta)
        out.append(dict(row, eventTimestamp=moment.strftime("%Y-%m-%dT%H:%M:%S.%fZ")))
    return out


@unittest.skipIf(who is None, "drift_engine is not installed (pip install -e '.[dev]')")
class _WhoBase(_Base):
    def public_for(self, rows, entries=None, anchors="default") -> bytes:
        result = self.inv_run(entries if entries is not None else nsg_drift(), rows, anchors=anchors)
        text, problems = inv.publish(result.document)
        self.assertEqual(problems, [])
        self.public_doc = result.document
        return text.encode()

    def who(self, public: bytes, rows=None, *, source=None, terraform=None, now=NOW, report=None, environ=None):
        source = source if source is not None else FakeSource({RG: [page(*(rows or []))]})
        return who.run_who(public, terraform if terraform is not None else state_json({NSG_ADDR: NSG_ID}),
                           source=source, now=now, report_bytes=report,
                           environ=NO_CI if environ is None else environ)

    def results(self, result) -> list[tuple]:
        return [(r["address"], r["op_id"], r["status"], r["callers"]) for r in result.document["results"]]


class CollectWindowTests(_WhoBase):
    def test_bounded_historic_window(self):
        rows = self.log.tags(at_time(8)) + self.log.tags(at_time(9))
        source = FakeSource({RG: [page(*rows)]})
        start = dt.datetime(2026, 10, 2, 7, 59, 59, 500000, tzinfo=UTC)
        end = dt.datetime(2026, 10, 2, 8, 0, 3, 200000, tzinfo=UTC)
        collection = al.collect_window(source, [(NSG_ADDR, al.parse_resource_id(NSG_ID))], start, end)
        self.assertIn("eventTimestamp ge '2026-10-02T07:59:59Z' and eventTimestamp le '2026-10-02T08:00:04Z'",
                      source.calls[0][1])
        self.assertEqual(len(collection.events), 2)  # the 09:00 group is outside the window
        self.assertEqual([m.relation for e in collection.events for m in e.matches], ["extension", "exact"])
        self.assertEqual(collection.scopes[0]["status"], "complete")
        self.assertEqual(collection.scopes[0]["dropped"], {"timestamp_outside_window": 2})
        self.assertNotIn(CALLER, json.dumps(collection.scopes))

    def test_bad_input(self):
        arm = al.parse_resource_id(NSG_ID)
        start = dt.datetime(2026, 10, 2, 8, tzinfo=UTC)
        for args in ([(NSG_ADDR, arm)], start.replace(tzinfo=None), start), \
                    ([(NSG_ADDR, arm)], start, start), \
                    ([(NSG_ADDR, arm)], start - dt.timedelta(days=90), start), \
                    ([(NSG_ADDR, al.parse_resource_id(f"/subscriptions/{SUB}"))], start, start + dt.timedelta(1)), \
                    ([(NSG_ADDR, None)], start, start + dt.timedelta(1)):
            with self.subTest(args=args[1:]), self.assertRaises(ValueError):
                al.collect_window(NoCallSource(), *args)
        with self.assertRaises(ValueError):
            al.collect_window(NoCallSource(), [(NSG_ADDR, arm)], start, start + dt.timedelta(1),
                              pipeline_principal="nope")

    def test_query_failure_is_reported_per_scope(self):
        source = FakeSource({RG: [al.SourceError("throttled", 429)]})
        collection = al.collect_window(source, [(NSG_ADDR, al.parse_resource_id(NSG_ID))],
                                       dt.datetime(2026, 10, 2, 8, tzinfo=UTC), dt.datetime(2026, 10, 2, 9, tzinfo=UTC))
        self.assertEqual((collection.scopes[0]["status"], collection.scopes[0]["error"]), ("failed", "throttled"))


class TerraformIdTests(_WhoBase):
    def test_both_shapes(self):
        ids = {NSG_ADDR: NSG_ID, RG_ADDR: RG_ID}
        self.assertEqual(who.terraform_resource_ids(state_json(ids)), ids)
        self.assertEqual(who.terraform_resource_ids(state_json(ids, nested=False)), ids)
        self.assertEqual(who.terraform_resource_ids(plan_json(ids)), ids)
        odd = json.dumps({"values": {"root_module": {"resources": [1, {"address": NSG_ADDR, "mode": "managed",
                                                                       "values": {"id": NSG_ID}}],
                                                    "child_modules": ["not a module"]}}}).encode()
        self.assertEqual(who.terraform_resource_ids(odd), {NSG_ADDR: NSG_ID})
        for bad in (b"[]", b'{"values": 1}', b"{", b'{"a": 1, "a": 2}'):
            with self.subTest(bad), self.assertRaises(ValueError):
                who.terraform_resource_ids(bad)


class MatchingTests(_WhoBase):
    def test_unique_match(self):
        rows = self.log.tags(at_time(8))
        public = self.public_for(rows)
        result = self.who(public, rows)
        self.assertEqual(self.results(result), [(NSG_ADDR, "op-1", "matched", [CALLER])])
        self.assertTrue(result.complete)
        self.assertEqual(result.document["public_binding"]["run_id"], "github-500-1")

    def test_no_match_and_multiple_matches(self):
        rows = self.log.tags(at_time(8))
        public = self.public_for(rows)
        self.assertEqual(self.results(self.who(public, []))[0][2], "no_match")
        twin = [dict(r, eventDataId=r["eventDataId"].replace("9000", "9100"), correlationId="corr-twin")
                for r in rows]
        result = self.who(public, rows + twin)
        self.assertEqual((self.results(result)[0][2], self.results(result)[0][3]), ("multiple_matches", []))
        self.assertFalse(result.complete)

    def test_timestamps_must_be_equal(self):
        rows = self.log.tags(at_time(8))
        public = self.public_for(rows)
        self.assertEqual(self.results(self.who(public, shift(rows, seconds=2)))[0][2], "no_match")  # outside +/- 1 s
        self.assertEqual(self.results(self.who(public, shift(rows, milliseconds=500)))[0][2], "no_match")  # inside, unequal

    def test_caller_type_and_client_must_match(self):
        rows = self.log.tags(at_time(8))
        public = self.public_for(rows)
        for claims in ({"idtyp": "user"}, {"appid": "c44b4083-3bb0-49c1-b47d-974e53cbdf3c"}):
            with self.subTest(claims):
                changed = [dict(r, claims=claims) for r in rows]
                self.assertEqual(self.results(self.who(public, changed))[0][2], "no_match")

    def test_operation_and_outcome_must_match(self):
        rows = self.log.tags(at_time(8))
        public = self.public_for(rows)
        renamed = [dict(r, operationName={"value": "Microsoft.Resources/tags/delete"}) for r in rows]
        self.assertEqual(self.results(self.who(public, renamed))[0][2], "no_match")
        failed = [dict(rows[0]), dict(rows[1], status={"value": "Failed"})]
        self.assertEqual(self.results(self.who(public, failed))[0][2], "no_match")

    def test_retention_and_query_failure(self):
        rows = self.log.tags(at_time(8))
        public = self.public_for(rows)
        result = self.who(public, source=NoCallSource(), now=at_time(8) + dt.timedelta(days=91))
        self.assertEqual(self.results(result)[0][2:], ("retention_exceeded", []))
        result = self.who(public, source=FakeSource({RG: [al.SourceError("authorization_failed", 403)]}))
        self.assertEqual(self.results(result)[0][2:], ("query_failed", []))

    def test_binding_failures_query_nothing(self):
        rows = self.log.tags(at_time(8))
        public = self.public_for(rows)
        leaky = public.replace(b'"github-500-1"', b'"alice@example.com"')
        contract = json.dumps({k: v for k, v in json.loads(public).items() if k != "rules"}).encode()
        other_report = report_bytes(self.plan(nsg_drift("other")))
        cases = {
            "invalid_json": dict(public=b"{"),
            "leak": dict(public=leaky),
            "contract": dict(public=contract),
            "binding_mismatch": dict(report=other_report),
            "address_unknown": dict(terraform=state_json({RG_ADDR: RG_ID})),
            "invalid_resource_id": dict(terraform=state_json({NSG_ADDR: "/not/an/id"})),
            "terraform_invalid": dict(terraform=b"not json"),
        }
        for detail, kwargs in cases.items():
            with self.subTest(detail):
                args = {"public": public, **kwargs}
                result = self.who(args.pop("public"), source=NoCallSource(), **args)
                self.assertEqual(result.document["failure"], {"code": "binding_failed", "detail": detail})
                self.assertEqual(result.document["results"], [])
        # the matching drift report passes
        ok = self.who(public, rows, report=report_bytes(self.plan(nsg_drift())))
        self.assertTrue(ok.complete)

    def test_resources_without_operations_need_no_id(self):
        public = self.public_for([], entries=nsg_drift())  # none found: no operations to look up
        result = self.who(public, source=NoCallSource(), terraform=state_json({}))
        self.assertEqual((result.document["failure"], result.document["results"], result.complete), (None, [], False))

    def test_refuses_in_github_actions(self):
        public = self.public_for(self.log.tags(at_time(8)))
        with self.assertRaises(who.WhoRefused):
            self.who(public, source=NoCallSource(), environ={"GITHUB_ACTIONS": "true"})


class WhoCliTests(_WhoBase):
    def main(self, args, source=None, env=None):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(cli, "_activity_log_source", return_value=source or FakeSource()), \
                mock.patch.object(cli, "_now", lambda: NOW), \
                mock.patch.dict(os.environ, env if env is not None else NO_CI, clear=True), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(args)
        return code, out.getvalue(), err.getvalue()

    def files(self, public: bytes, terraform: bytes | None = None) -> list[str]:
        directory = self.dir("who-in")
        paths = [os.path.join(directory, "public.json"), os.path.join(directory, "state.json")]
        for path, data in zip(paths, (public, terraform or state_json({NSG_ADDR: NSG_ID}))):
            with open(path, "wb") as fh:
                fh.write(data)
        self.out_dir = os.path.join(self.tmp, "who-out")
        return ["who", "--public", paths[0], "--terraform", paths[1], "--output-dir", self.out_dir]

    def test_prints_the_recorded_caller_and_writes_a_private_file(self):
        rows = self.log.tags(at_time(8))
        args = self.files(self.public_for(rows))
        code, out, err = self.main(args, FakeSource({RG: [page(*rows)]}))
        self.assertEqual(code, 0, err)
        self.assertIn(f"recorded caller: {CALLER}", out)
        self.assertIn("not proof of who caused the drift", out)
        target = os.path.join(self.out_dir, who.WHO_FILE)
        self.assertEqual(stat.S_IMODE(os.stat(self.out_dir).st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(os.stat(target).st_mode), 0o600)
        self.assertEqual(os.listdir(self.out_dir), [who.WHO_FILE])
        self.assertEqual(json.load(open(target))["results"][0]["callers"], [CALLER])

    def test_failures_print_no_caller(self):
        rows = self.log.tags(at_time(8))
        args = self.files(self.public_for(rows))
        code, out, err = self.main(args, FakeSource({RG: [page()]}))
        self.assertEqual(code, 1)
        self.assertNotIn(CALLER, out + err)
        args = self.files(self.public_for(rows), terraform=state_json({}))
        code, out, err = self.main(args, NoCallSource())
        self.assertEqual(code, 1)
        self.assertIn("WHO LOOKUP FAILED [binding_failed: address_unknown]", err)

    def test_refuses_in_github_actions_and_writes_nothing(self):
        args = self.files(self.public_for(self.log.tags(at_time(8))))
        code, out, err = self.main(args, NoCallSource(), env={"GITHUB_ACTIONS": "true"})
        self.assertEqual(code, 2)
        self.assertIn("local-only", err)
        self.assertFalse(os.path.exists(self.out_dir))

    def test_symlink_targets_are_refused(self):
        rows = self.log.tags(at_time(8))
        args = self.files(self.public_for(rows))
        os.makedirs(self.out_dir)
        decoy = os.path.join(self.tmp, "decoy.json")
        open(decoy, "w").close()
        os.symlink(decoy, os.path.join(self.out_dir, who.WHO_FILE))
        code, _, err = self.main(args, FakeSource({RG: [page(*rows)]}))
        self.assertEqual(code, 73)
        self.assertEqual(open(decoy).read(), "")
        linked = os.path.join(self.tmp, "linked-dir")
        os.symlink(self.dir("real-dir"), linked)
        args[args.index("--output-dir") + 1] = linked
        self.assertEqual(self.main(args, FakeSource({RG: [page(*rows)]}))[0], 73)

    def test_unreadable_inputs(self):
        args = self.files(self.public_for(self.log.tags(at_time(8))))
        args[args.index("--terraform") + 1] = os.path.join(self.tmp, "missing.json")
        self.assertEqual(self.main(args, NoCallSource())[0], 2)
        args = self.files(self.public_for(self.log.tags(at_time(8)))) + ["--report", os.path.join(self.tmp, "nope")]
        self.assertEqual(self.main(args, NoCallSource())[0], 2)

    def test_write_error(self):
        rows = self.log.tags(at_time(8))
        args = self.files(self.public_for(rows))
        blocker = os.path.join(self.tmp, "a-file")
        open(blocker, "w").close()
        args[args.index("--output-dir") + 1] = os.path.join(blocker, "sub")
        code, _, err = self.main(args, FakeSource({RG: [page(*rows)]}))
        self.assertEqual(code, 73)
        self.assertNotIn(CALLER, err)


if __name__ == "__main__":
    unittest.main()
