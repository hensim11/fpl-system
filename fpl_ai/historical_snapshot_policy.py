"""One explicitly authorized, versioned superseded-deadline exception."""
import re

from fpl_ai.errors import FPLValidationError
from fpl_ai.historical_transform import parse_utc, utc_string


def validate_superseded_policy(policy, season):
    fields = {'policy_version', 'exception_type', 'season', 'gameweek', 'source_path',
              'source_sha256', 'resolved_commit_sha', 'capture_time_utc',
              'payload_deadline_utc', 'authoritative_deadline_utc', 'reason'}
    if not isinstance(policy, dict) or set(policy) != fields:
        raise FPLValidationError('malformed superseded-deadline exception')
    if (type(policy['policy_version']) is not int or policy['policy_version'] != 1
            or policy['exception_type'] != 'superseded_deadline'
            or policy['season'] != season or season != '2021-22'
            or type(policy['gameweek']) is not int or policy['gameweek'] != 18):
        raise FPLValidationError('superseded-deadline policy v1 is scoped only to 2021-22 GW18')
    for key, length in (('source_sha256', 64), ('resolved_commit_sha', 40)):
        if not isinstance(policy[key], str) or not re.fullmatch('[0-9a-f]{%d}' % length, policy[key]):
            raise FPLValidationError(f'invalid superseded-deadline {key}')
    if policy['source_path'] != 'cache/2021/12/18/1233.json.xz':
        raise FPLValidationError('superseded-deadline v1 requires the pinned 12:33 path')
    for key in ('capture_time_utc', 'payload_deadline_utc', 'authoritative_deadline_utc'):
        value = policy[key]
        if not isinstance(value, str) or utc_string(parse_utc(value, key)) != value:
            raise FPLValidationError(f'invalid superseded-deadline {key}')
    if (policy['capture_time_utc'] != '2021-12-18T12:33:00Z'
            or policy['payload_deadline_utc'] != '2021-12-18T13:30:00Z'
            or policy['authoritative_deadline_utc'] != '2021-12-18T16:00:00Z'):
        raise FPLValidationError('superseded-deadline v1 timestamps differ from the authorized case')
    capture, payload, final = (parse_utc(policy[k], k) for k in
                               ('capture_time_utc', 'payload_deadline_utc', 'authoritative_deadline_utc'))
    if not capture < payload < final:
        raise FPLValidationError('superseded-deadline capture must precede both deadlines')
    if not isinstance(policy['reason'], str) or not policy['reason'].strip():
        raise FPLValidationError('superseded-deadline exception requires a reason')


def accept_superseded_snapshot(policy, season, gameweek, path, capture, deadline, payload, record):
    validate_superseded_policy(policy, season)
    if (gameweek != policy['gameweek'] or path != policy['source_path']
            or utc_string(capture) != policy['capture_time_utc']
            or utc_string(deadline) != policy['authoritative_deadline_utc']
            or record.get('sha256') != policy['source_sha256']
            or record.get('source_path') != path
            or record.get('requested_season') != season
            or record.get('resolved_commit_sha') != policy['resolved_commit_sha']):
        raise FPLValidationError('superseded-deadline evidence does not exactly match policy')
    events = payload.get('events') if isinstance(payload, dict) else None
    if not isinstance(events, list) or any(not isinstance(e, dict) for e in events):
        raise FPLValidationError('malformed superseded-deadline events')
    if any(type(e.get('is_next')) is not bool for e in events):
        raise FPLValidationError('malformed superseded-deadline upcoming flags')
    target = [e for e in events if e.get('id') == gameweek]
    upcoming = [e for e in events if e.get('is_next') is True]
    if (len(target) != 1 or len(upcoming) != 1 or upcoming[0] is not target[0]
            or type(target[0].get('id')) is not int
            or target[0].get('is_next') is not True
            or target[0].get('deadline_time') != policy['payload_deadline_utc']):
        raise FPLValidationError('superseded-deadline event identity/deadline/upcoming flags mismatch')
    payload_deadline = parse_utc(target[0]['deadline_time'], 'payload deadline')
    if not capture < payload_deadline or not capture < deadline:
        raise FPLValidationError('superseded-deadline snapshot is not strictly pre-deadline')
    return {**policy, 'hours_before_authoritative_deadline': (deadline - capture).total_seconds() / 3600,
            'hours_before_payload_deadline': (payload_deadline - capture).total_seconds() / 3600,
            'state_as_of_utc': utc_string(capture)}
