"""Conservative scope guard for the structural-calculation refinement."""
import re
from filing_features import decision

THERMAL=re.compile(r'thermal|energy|топло|термич|енерги',re.IGNORECASE)


def choose(base,proposed):
    base=decision(base);proposed=decision(proposed)
    # Structural-report grouping must not erase separate thermal/energy outputs.
    # Use only model-read content; no source filenames or human labels are inputs.
    visible=' '.join(str(row.get(key,'')) for row in (base,proposed)
                     for key in ('left_heading','right_heading','evidence'))
    if base['new_document'] and not proposed['new_document'] and THERMAL.search(visible):
        return {**base,'refinement_policy':'preserved_thermal_scope'}
    return {**proposed,'refinement_policy':'accepted_v7'}
