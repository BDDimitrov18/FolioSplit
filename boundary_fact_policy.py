"""V8b fact policy: recognize a fresh thermal output after an earlier thermal output."""
from boundary_facts import SCHEMA,prompt,candidate_reason,recovery as original_recovery


def recovery(facts):
    rule=original_recovery(facts)
    if rule:return rule
    if (facts['confidence']>=90 and facts['right_first_page']
            and facts['left_role']=='thermal_output' and facts['right_role']=='thermal_output'):
        return 'thermal_output_restart'
    return None


def recover_decision(base,facts):
    rule=recovery(facts)
    if not rule:return {**base,'fact_recovery':None}
    return {**base,'new_document':True,'relationship':'independent',
            'confidence':facts['confidence'],'fact_recovery':rule}
