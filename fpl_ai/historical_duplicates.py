"""Exact, hash-bound duplicate source-row policy; never resolve conflicting rows."""

import re
from collections import defaultdict

from fpl_ai.errors import FPLValidationError
from fpl_ai.historical_io import sha256_bytes


def validate_duplicate_policy(policy, season):
    fields = {'policy_version', 'season', 'source_path', 'resolved_commit_sha', 'source_sha256', 'source_row_count', 'duplicates', 'reason'}
    if not isinstance(policy, dict) or set(policy) != fields:
        raise FPLValidationError('malformed exact duplicate row policy')
    if type(policy['policy_version']) is not int or policy['policy_version'] != 1 or policy['season'] != season:
        raise FPLValidationError('exact duplicate row policy version or season mismatch')
    if policy['source_path'] != f'data/{season}/gws/merged_gw.csv':
        raise FPLValidationError('exact duplicate row policy must name season merged_gw.csv')
    for field, length in [('resolved_commit_sha', 40), ('source_sha256', 64)]:
        if not isinstance(policy[field], str) or not re.fullmatch('[0-9a-f]{'+str(length)+'}', policy[field]):
            raise FPLValidationError('invalid exact duplicate row source identity')
    if type(policy['source_row_count']) is not int or policy['source_row_count'] < 1:
        raise FPLValidationError('invalid exact duplicate source row count')
    if not isinstance(policy['reason'], str) or not policy['reason'].strip():
        raise FPLValidationError('exact duplicate row policy requires evidence reason')
    if not isinstance(policy['duplicates'], list) or not policy['duplicates']:
        raise FPLValidationError('exact duplicate row policy requires explicit keys')
    keys = set()
    for entry in policy['duplicates']:
        if not isinstance(entry, dict) or set(entry) != {'element', 'fixture', 'gameweek', 'occurrences'}:
            raise FPLValidationError('malformed exact duplicate row key')
        if any(type(v) is not int or v < 1 for v in entry.values()) or entry['occurrences'] < 2:
            raise FPLValidationError('invalid exact duplicate row key counts')
        key = entry['element'], entry['fixture']
        if key in keys:
            raise FPLValidationError('duplicate policy key')
        keys.add(key)


def filter_exact_duplicates(value, rows, policy, season):
    """Return original row numbers, preserving one copy only for exact declared repeats."""
    validate_duplicate_policy(policy, season)
    if sha256_bytes(value) != policy['source_sha256'] or len(rows) != policy['source_row_count']:
        raise FPLValidationError('exact duplicate source hash or row count mismatch')
    groups = defaultdict(list)
    for number, row in enumerate(rows, 2):
        groups[row.get('element'), row.get('fixture')].append((number, row))
    declared = {(str(e['element']), str(e['fixture'])): e for e in policy['duplicates']}
    observed = {key for key, group in groups.items() if len(group) > 1}
    if observed != set(declared):
        raise FPLValidationError('undeclared or stale exact duplicate row policy')
    omitted, evidence = set(), []
    for key, rule in declared.items():
        group = groups[key]
        first = group[0][1]
        if (len(group) != rule['occurrences'] or first.get('GW') != str(rule['gameweek'])
                or any(row != first for _, row in group)):
            raise FPLValidationError('conflicting or changed exact duplicate source rows')
        removed = [number for number, _ in group[1:]]
        omitted.update(removed)
        evidence.append({**rule, 'retained_source_row': group[0][0], 'omitted_source_rows': removed})
    return [(number, row) for number, row in enumerate(rows, 2) if number not in omitted], {
        'policy': policy, 'removed_row_count': len(omitted), 'duplicates': evidence,
        'comparison': 'all raw CSV fields exactly equal, including ignored and forbidden fields',
    }
