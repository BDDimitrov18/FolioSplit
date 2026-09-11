"""Narrow visual check for structural software plots mistaken for issued drawings."""
import re
from model_options import validate_query_fields

KINDS={'calculation_page','structural_software_plot','independent_drawing','other'}
SCHEMA={'left_kind':str,'right_kind':str,'same_structure':bool,
        'right_independent_titleblock':bool,'evidence':str,'confidence':'confidence'}


def candidate_reason(data):
    if not data['new_document']:return None
    text=' '.join(str(data.get(k,'')) for k in ('left_heading','right_heading','evidence'))
    if re.search(r'\bslab\b|plan view|SAFE\b|software.output|reinforcement.plot|армировка',text,re.I):
        return 'possible_structural_software_plot'
    return None


def prompt(left,right):
    return f'''Read INPUT IMAGE 1 (page {left}) and INPUT IMAGE 2 (page {right}) in
that order. Extract facts about structural calculation outputs. Do not decide
whether every different plot quantity is a separately filed document.

Classify each image independently:
- calculation_page: structural numeric calculations, input data or element checks;
- structural_software_plot: a generated model/load/reinforcement/result plot,
  possibly with a program name/version, quantity, units, legend or print timestamp;
- independent_drawing: an issued drawing sheet with its own drawing identity;
- other: another type or uncertain.
A software header ('Plan View', 'Slab Resultant', load-case name, M11/M22/M12,
units/color scale, SAFE/ETABS version or print footer) is NOT an independent
engineering title block. A stamp alone is not a title block either. A genuine
independent title block identifies the drawing/project/sheet and usually its
scale, drawing number or revision and designer roles.

same_structure must be supported by matching visible structural grid, geometry,
model identification or explicit project/element references on BOTH pages.
A shared engineer's stamp alone is insufficient. Do not invent unreadable IDs.
If the left page lacks enough structure-specific evidence, answer false.
Return only JSON; evidence <=30 words:
{{"left_kind":"one kind","right_kind":"one kind","same_structure":true/false,
"right_independent_titleblock":true/false,"evidence":"visible evidence","confidence":0-100}}.
'''


def recovery(facts):
    validate_query_fields(facts,SCHEMA)
    if facts['left_kind'] not in KINDS or facts['right_kind'] not in KINDS:raise ValueError('Unknown plot kind')
    if (facts['confidence']>=90 and facts['same_structure'] and not facts['right_independent_titleblock']
            and facts['left_kind'] in {'calculation_page','structural_software_plot'}
            and facts['right_kind']=='structural_software_plot'):
        return 'same_structural_output'
    return None


def recover_decision(base,facts):
    rule=recovery(facts)
    if not rule:return {**base,'plot_rule':None}
    return {**base,'new_document':False,'relationship':'continuation','plot_rule':rule}
