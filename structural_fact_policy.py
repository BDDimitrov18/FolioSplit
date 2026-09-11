"""Scope guards for structural-body facts; preserve more specific document types."""
import re
from structural_facts import SCHEMA, prompt, candidate_reason as original_candidate, recovery

QUANTITIES = re.compile(r'количествена\s+сметка|bill\s+of\s+quantities|quantity\s+schedule', re.I)
REPORT = re.compile(r'обследване|становище|доклад|survey\s+report', re.I)
PROJECT = re.compile(r'обект|проект|project', re.I)


def protected(base):
    if base.get('fact_recovery') in {'thermal_output_restart','narrative_to_thermal_output'}:
        return 'typed_thermal_output'
    if base.get('page_type_confidence', 0) >= 90:
        if any(base.get(side + '_kind', 'other') != 'other' for side in ('left', 'right')):
            return 'specific_non_calculation_type'
        if any(QUANTITIES.search(base.get(side + '_heading', '')) for side in ('left', 'right')):
            return 'quantity_schedule'
        heading = base.get('right_heading', '')
        if REPORT.search(heading) and PROJECT.search(heading):
            return 'separate_report_title'
    return None


def candidate_reason(base):
    return None if protected(base) else original_candidate(base)


def recover_decision(base, facts):
    guard = protected(base)
    rule = None if guard else recovery(facts)
    if not rule:
        return {**base, 'structural_rule': None, 'structural_guard': guard}
    return {**base, 'new_document': False, 'relationship': 'section',
            'confidence': facts['confidence'], 'structural_rule': rule}
