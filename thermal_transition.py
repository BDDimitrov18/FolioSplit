"""Require a completed thermal report and a visibly fresh output before recovery."""
import re
from model_options import validate_query_fields

SCHEMA={'left_heading':str,'right_heading':str,'left_closing_summary':bool,
        'right_output':str,'evidence':str,'confidence':'confidence'}


def needed(base,facts):
    if base['new_document'] or facts['confidence']<90:return False
    if facts['right_role']!='thermal_output' or facts['left_role'] not in {'thermal_output','narrative'}:return False
    appendix=(re.search(r'извод|заключен|conclu',base['left_heading'],re.I)
              and re.search(r'приложен|appendix|детайл',base['right_heading'],re.I))
    return bool(facts['right_first_page'] or appendix)


def prompt(left,right):
    return f'''Read INPUT IMAGE 1 (source page {left}) and INPUT IMAGE 2 (page {right}).
Extract visible facts about the transition between thermal/energy report outputs.

left_closing_summary is true only for the completed report's concluding summary:
final overall energy class/compliance/result, concluding wording and a closing
engineer/date/signature block. A regular page stamp, repeated footer, reference
U-value table or intermediate calculation alone is NOT a closing summary.

right_output must be one of:
- fresh_calculation: its own calculation heading and introductory parameters or
  initial tables; not merely the next numbered interior subsection;
- fresh_details: a newly introduced appendix/detail set, with its own heading and
  initial detail/element numbering (for example detail 1), containing calculations
  or construction details. Calling it ПРИЛОЖЕНИЕ/appendix does not prevent it from
  being the beginning of a fresh detail set;
- continuation: ongoing table rows, further numbered details, or an interior page;
- uncertain: visible evidence does not establish the type.
Transcribe both actual headings; do not infer one image's content from the other.
Return JSON only, with <=35 words of evidence:
{{"left_heading":"literal or empty","right_heading":"literal or empty",
"left_closing_summary":true/false,"right_output":"one type",
"evidence":"visible evidence","confidence":0-100}}.
'''


def recover_decision(base,facts):
    validate_query_fields(facts,SCHEMA)
    if facts['right_output'] not in {'fresh_calculation','fresh_details','continuation','uncertain'}:raise ValueError('Unknown thermal output')
    rule=(facts['confidence']>=90 and facts['left_closing_summary']
          and facts['right_output'] in {'fresh_calculation','fresh_details'})
    return {**base,'new_document':bool(base['new_document'] or rule),
            'relationship':'independent' if base['new_document'] or rule else base['relationship'],
            'confidence':facts['confidence'] if rule else base['confidence'],
            'thermal_rule':'completed_report_to_fresh_output' if rule else 'preserve_base'}
