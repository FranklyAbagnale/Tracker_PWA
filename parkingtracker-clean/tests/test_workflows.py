"""Guard rails for GitHub Actions usage.

The account has a small monthly Actions-minutes allowance and the app commits to
the repo many times per save (photo, vehicle, plate, index). If any workflow
reacts to those commits, usage grows with the number of users. These tests fail
if a workflow is added or edited in a way that could do that.
"""
import fnmatch
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.y*ml"))

# Events whose frequency is controlled by the repo owner, not by app users.
ALLOWED_EVENTS = {"push", "pull_request", "workflow_dispatch"}
# Paths the field app writes to. A push trigger must never match these.
APP_WRITTEN_PATHS = [
    "data/index.json",
    "data/vehicles/VEH_00000000.json",
    "data/plates/ABC1234.json",
    "photos/VEH_00000000_20261010T000000_001.jpg",
]
MAX_JOB_TIMEOUT_MIN = 10


def load(path):
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    # PyYAML (YAML 1.1) parses the key `on` as boolean True.
    triggers = doc.get("on", doc.get(True))
    if isinstance(triggers, str):
        triggers = {triggers: None}
    elif isinstance(triggers, list):
        triggers = {t: None for t in triggers}
    return doc, triggers or {}


def path_matches(pattern, path):
    """Approximate GitHub's glob: ** crosses directories, * does not."""
    if pattern.startswith("!"):
        return False
    regex = fnmatch.translate(pattern.replace("**", "\0").replace("*", "[^/]*").replace("\0", "*"))
    return fnmatch.fnmatchcase(path, pattern.replace("**", "*")) or bool(__import__("re").match(regex, path))


class WorkflowBudgetTests(unittest.TestCase):
    def test_there_are_workflows_to_check(self):
        self.assertTrue(WORKFLOWS, "no workflows found; is the path right?")

    def test_only_owner_controlled_events(self):
        for wf in WORKFLOWS:
            _, triggers = load(wf)
            self.assertLessEqual(set(triggers), ALLOWED_EVENTS, f"{wf.name}: unexpected trigger(s) {set(triggers) - ALLOWED_EVENTS}")

    def test_no_schedules(self):
        for wf in WORKFLOWS:
            _, triggers = load(wf)
            self.assertNotIn("schedule", triggers, f"{wf.name}: scheduled runs burn minutes whether or not anyone uses the app")

    def test_push_triggers_are_path_filtered_and_never_match_app_writes(self):
        for wf in WORKFLOWS:
            _, triggers = load(wf)
            if "push" not in triggers:
                continue
            push = triggers["push"] or {}
            patterns = push.get("paths")
            self.assertTrue(patterns, f"{wf.name}: a push trigger needs a `paths` filter (every app save is a push)")
            for pattern in patterns:
                for written in APP_WRITTEN_PATHS:
                    self.assertFalse(path_matches(pattern, written),
                                     f"{wf.name}: push path {pattern!r} matches {written}, which the app writes on every save")

    def test_every_job_is_capped_and_uses_the_cheapest_runner(self):
        for wf in WORKFLOWS:
            doc, _ = load(wf)
            for name, job in doc["jobs"].items():
                self.assertEqual(job.get("runs-on"), "ubuntu-latest", f"{wf.name}/{name}: Windows and macOS runners cost 2x and 10x")
                timeout = job.get("timeout-minutes")
                self.assertIsNotNone(timeout, f"{wf.name}/{name}: set timeout-minutes so a hung job cannot drain the allowance")
                self.assertLessEqual(timeout, MAX_JOB_TIMEOUT_MIN, f"{wf.name}/{name}: timeout too generous")

    def test_bursts_collapse_into_one_run(self):
        for wf in WORKFLOWS:
            doc, triggers = load(wf)
            if not ({"push", "pull_request"} & set(triggers)):
                continue
            concurrency = doc.get("concurrency")
            self.assertIsInstance(concurrency, dict, f"{wf.name}: add `concurrency` so rapid pushes do not queue extra runs")
            self.assertTrue(concurrency.get("cancel-in-progress"), f"{wf.name}: cancel-in-progress must be true")

    def test_path_matcher_self_check(self):
        self.assertTrue(path_matches("data/**", "data/vehicles/VEH_00000000.json"))
        self.assertTrue(path_matches("photos/**", "photos/x.jpg"))
        self.assertTrue(path_matches("data/vehicles/**", "data/vehicles/VEH_00000000.json"))
        self.assertFalse(path_matches("web/**", "data/index.json"))
        self.assertFalse(path_matches("scripts/**", "data/index.json"))


if __name__ == "__main__":
    unittest.main()
