"""Experimental typed verification of internal structural-calculation transitions."""
import re
from model_options import validate_query_fields

SCHEMA = {'left_kind': str, 'right_kind': str, 'different_project_reference': bool,
          'evidence': str, 'confidence': 'confidence'}
KINDS = {'structural_calculation_body', 'thermal_calculation', 'report_cover',
         'explanatory_note', 'independent_drawing', 'other'}


def candidate_reason(decision):
    if not decision['new_document']:
        return None
    text = ' '.join(decision.get(k, '') for k in ('left_heading', 'right_heading', 'evidence'))
    if re.search(r'structural|frame|reinforc|армиров|рамк|шайб|оразмер|конструк|calculation|изчисл|slab|steel|tower|radinex|column|foundation', text, re.I):
        return 'possible_internal_structural_calculation'
    return None


def prompt(left, right):
    return f'''Read INPUT IMAGE 1 (source page {left}) and INPUT IMAGE 2 (page {right})
independently. Extract page types, not a document-splitting verdict.
Kinds: structural_calculation_body, thermal_calculation, report_cover,
explanatory_note, independent_drawing, other.
structural_calculation_body means substantive structural computations or their
input/result tables and plots: frames, walls, beams, columns, slabs, reinforcement,
foundations, loads, sizing, software model inputs and element checks. A different
frame/wall/axis/floor or a new computation subsection does not change this type.
A report_cover is a distinct introductory title sheet with project/discipline,
designer/phase/date fields, not a technical page already containing computations.
An explanatory_note is narrative design explanation, not calculation output.
An independent_drawing has its own drawing sheet title block/number; a small
structural schematic embedded beside computations is calculation body.
Thermal/energy/HVAC heat-load output is thermal_calculation, never structural.
Set different_project_reference true only when the images visibly identify
DIFFERENT construction projects or issued report identifiers. Different structural
element identifiers (frame X_7 vs X_9, wall 8 vs 9, etc.), load cases, program
headings and page numbers do not establish a different project. When identifiers
are absent, set false; do not invent a match. Explain visible facts in <=25 words.
Return JSON only:
{{"left_kind":"one kind","right_kind":"one kind",
"different_project_reference":true/false,"evidence":"visible facts","confidence":0-100}}.
'''


def recovery(facts):
    validate_query_fields(facts, SCHEMA)
    if facts['left_kind'] not in KINDS or facts['right_kind'] not in KINDS:
        raise ValueError('Unknown structural page kind')
    if (facts['confidence'] >= 90 and not facts['different_project_reference']
            and facts['left_kind'] == facts['right_kind'] == 'structural_calculation_body'):
        return 'internal_structural_calculation'
    return None
