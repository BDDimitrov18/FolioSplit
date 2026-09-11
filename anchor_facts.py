"""Experimental recovery using a frozen predicted document start as context."""
import re
from model_options import validate_query_fields

SCHEMA = {'anchor_heading': str, 'right_heading': str, 'anchor_kind': str,
          'right_kind': str, 'right_fresh_start': bool, 'evidence': str,
          'confidence': 'confidence'}
KINDS = {'technical_assignment', 'contents', 'explanatory_note', 'quantity_schedule',
         'tree_inventory', 'waste_plan', 'other'}


def candidate_reason(decision):
    if decision['new_document']:
        return None
    if re.search(r'дендролог|количествен|об[яъ]снителна.*записка|план\s+за\s+управление\s+на\s+отпадъц',
                 decision['right_heading'], re.I):
        return 'named_artifact_inside_predicted_document'
    return None


def prompt(anchor, right):
    return f'''INPUT IMAGE 1 is source page {anchor}, the predicted beginning of
an existing document. INPUT IMAGE 2 is source page {right}, a later candidate
start. These images are NOT necessarily adjacent. Read each independently.
Extract visible artifact types, not a generic split decision.
Kinds: technical_assignment, contents, explanatory_note, quantity_schedule,
tree_inventory, waste_plan, other.
A technical_assignment specifies what a designer MUST prepare or requirements
for a future project. A contents page indexes material already in the folder;
a list of required deliverables inside an assignment is not a contents index.
A quantity_schedule lists work/material quantities. A tree_inventory lists tree
species/individual plants and dimensions, condition or identification.
right_fresh_start requires its own actual heading plus introductory text or
initial table headings/entries; repeated headings over continuing rows do not
establish a new start. Transcribe visible headings, never borrow across images.
Return JSON only, evidence <=35 words:
{{"anchor_heading":"literal or empty","right_heading":"literal or empty",
"anchor_kind":"one kind","right_kind":"one kind","right_fresh_start":true/false,
"evidence":"visible facts","confidence":0-100}}.
'''


def recovery(facts):
    validate_query_fields(facts, SCHEMA)
    if facts['anchor_kind'] not in KINDS or facts['right_kind'] not in KINDS:
        raise ValueError('Unknown anchor artifact kind')
    if facts['confidence'] < 90 or not facts['right_fresh_start']:
        return None
    pair = facts['anchor_kind'], facts['right_kind']
    if pair == ('technical_assignment', 'explanatory_note'):
        return 'assignment_to_explanatory_note'
    if pair == ('quantity_schedule', 'tree_inventory'):
        return 'quantity_schedule_to_tree_inventory'
    return None
