"""Exact superseded-deadline eligibility; the general rule remains strict."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from fpl_ai.errors import FPLValidationError
from fpl_ai.historical_pipeline import (
    _valid_snapshot, _select_snapshots, create_build_identity,
    load_source_catalogue, run_historical_pipeline,
)
from fpl_ai.historical_snapshot_policy import accept_superseded_snapshot, validate_superseded_policy
from fpl_ai.historical_transform import parse_utc


class SupersededDeadlineTests(unittest.TestCase):
    def setUp(self):
        self.catalogue = load_source_catalogue()
        self.config = self.catalogue['seasons']['2021-22']
        self.policy = copy.deepcopy(self.config['superseded_deadline_exception'])
        data = json.loads((Path(__file__).parent / 'fixtures/historical_2021_22/superseded_deadline_snapshot.json').read_text())
        self.payload, self.record = data['payload'], data['record']
        self.capture = parse_utc(self.policy['capture_time_utc'], 'capture')
        self.deadline = parse_utc(self.policy['authoritative_deadline_utc'], 'deadline')

    def accept(self, **changes):
        args = dict(policy=self.policy, season='2021-22', gameweek=18,
                    path=self.policy['source_path'], capture=self.capture,
                    deadline=self.deadline, payload=self.payload, record=self.record)
        args.update(changes)
        return accept_superseded_snapshot(**args)

    def test_exact_source_is_accepted_with_explicit_freshness_evidence(self):
        evidence = self.accept()
        self.assertEqual(evidence['state_as_of_utc'], '2021-12-18T12:33:00Z')
        self.assertEqual(evidence['hours_before_authoritative_deadline'], 3.45)
        self.assertEqual(evidence['hours_before_payload_deadline'], 0.95)
        self.assertEqual(evidence['source_sha256'], self.record['sha256'])
        self.assertEqual(evidence['exception_type'], 'superseded_deadline')
        self.assertEqual(self.payload['events'][17]['deadline_time'], '2021-12-18T13:30:00Z')

    def test_runtime_identifiers_must_all_match(self):
        changes = [{'season': '2022-23'}, {'gameweek': 17}, {'path': 'cache/2021/12/18/0626.json.xz'},
                   {'capture': parse_utc('2021-12-18T12:32:00Z', 'capture')},
                   {'deadline': parse_utc('2021-12-18T16:01:00Z', 'deadline')}]
        for field, value in [('sha256', 'a' * 64), ('source_path', 'wrong'),
                             ('requested_season', '2022-23'), ('resolved_commit_sha', 'a' * 40)]:
            changes.append({'record': dict(self.record, **{field: value})})
        for change in changes:
            with self.subTest(change=change), self.assertRaises(FPLValidationError):
                self.accept(**change)

    def test_event_deadline_identity_next_flags_and_ambiguity_rejected(self):
        for field, value in [('deadline_time', '2021-12-18T13:31:00Z'), ('id', 19), ('is_next', False), ('is_next', 1)]:
            payload = copy.deepcopy(self.payload); payload['events'][17][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(FPLValidationError):
                self.accept(payload=payload)
        for duplicate in (True, False):
            payload = copy.deepcopy(self.payload)
            if duplicate:
                payload['events'].append(copy.deepcopy(payload['events'][17]))
            else:
                payload['events'][18]['is_next'] = True
            with self.assertRaises(FPLValidationError):
                self.accept(payload=payload)

    def test_postdeadline_and_other_mismatches_stay_rejected(self):
        late = parse_utc('2021-12-18T18:25:00Z', 'capture')
        with self.assertRaises(FPLValidationError):
            self.accept(capture=late, path='cache/2021/12/18/1825.json.xz')
        self.assertFalse(_valid_snapshot(self.payload, 18, self.deadline, self.capture))
        payload = copy.deepcopy(self.payload)
        payload['events'][17]['deadline_time'] = '2021-12-18T16:00:00Z'
        self.assertTrue(_valid_snapshot(payload, 18, self.deadline, self.capture))
        self.assertFalse(_valid_snapshot(payload, 18, self.deadline, late))
        for gw in (17, 19):
            self.assertFalse(_valid_snapshot(self.payload, gw, self.deadline, self.capture))

    def test_configuration_is_narrow_versioned_and_hashed(self):
        before = create_build_identity('2021-22', self.config, self.catalogue['schema_version'])
        self.assertEqual(before['snapshot_selection']['superseded_deadline_exception'], self.policy)
        changed = copy.deepcopy(self.config)
        changed['superseded_deadline_exception']['reason'] += ' Additional audit detail.'
        self.assertNotEqual(before, create_build_identity('2021-22', changed, self.catalogue['schema_version']))
        for field, value in [('season', '2022-23'), ('gameweek', 19), ('policy_version', 2),
                             ('source_path', 'other'), ('source_sha256', 'invalid'),
                             ('capture_time_utc', '2021-12-18T12:32:00Z'),
                             ('payload_deadline_utc', '2021-12-18T13:31:00Z'),
                             ('authoritative_deadline_utc', '2021-12-18T16:01:00Z'), ('reason', '')]:
            policy = dict(self.policy, **{field: value})
            with self.subTest(field=field), self.assertRaises(FPLValidationError):
                validate_superseded_policy(policy, '2021-22')
        policy = dict(self.policy, source_sha256='a' * 64)
        with self.assertRaises(FPLValidationError):
            self.accept(policy=policy)

    def test_malformed_policy_cannot_fetch_or_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); catalogue = copy.deepcopy(self.catalogue)
            catalogue['seasons']['2021-22']['superseded_deadline_exception']['gameweek'] = 19
            path = root / 'sources.json'; path.write_text(json.dumps(catalogue))
            with self.assertRaises(FPLValidationError):
                run_historical_pipeline('2021-22', root, source_catalogue_path=path,
                                        fetcher=lambda url: self.fail('unexpected download'))
            self.assertFalse((root / 'historical/catalogue.json').exists())
            self.assertFalse((root / 'historical/processed').exists())

    def test_missing_or_stale_exception_is_not_silently_ignored(self):
        with self.assertRaisesRegex(FPLValidationError, 'not used'):
            _select_snapshots([18], {18: self.deadline}, [],
                              self.config['sources']['fplcache'], None,
                              season='2021-22', exception=self.policy)

    def test_failed_evidence_selection_retains_failure_without_publication(self):
        from tests.test_historical_pipeline import synthetic_sources
        values, catalogue = synthetic_sources()
        catalogue = json.loads(json.dumps(catalogue).replace('2024-25', '2021-22'))
        catalogue['seasons']['2021-22']['superseded_deadline_exception'] = dict(
            self.policy, resolved_commit_sha=catalogue['seasons']['2021-22']['sources']['fplcache']['resolved_commit_sha'])
        values = {url.replace('2024-25', '2021-22'): data for url, data in values.items()}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); config = root / 'sources.json'; config.write_text(json.dumps(catalogue))
            with self.assertRaisesRegex(FPLValidationError, 'not used'):
                run_historical_pipeline('2021-22', root, source_catalogue_path=config,
                                        fetcher=values.__getitem__)
            self.assertFalse((root / 'historical/catalogue.json').exists())
            self.assertFalse((root / 'historical/processed').exists())
            failures = list((root / 'historical/failed/2021-22').glob('*.json'))
            self.assertEqual(len(failures), 1)
            report = json.loads(failures[0].read_text())
            self.assertEqual(report['failures'], ['snapshots.selection'])
            self.assertFalse(report['catalogue_updated'])
