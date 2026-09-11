"""Frozen artifact transition rules; evidence comes from independent page reads."""

import re

from model_options import validate_query_fields

SCHEMA={'anchor_kind':str,'left_kind':str,'right_kind':str,
        'anchor_heading':str,'left_heading':str,'right_heading':str,
        'right_fresh_start':bool,'right_explicit_contract_annex':bool,
        'right_drawing_titleblock':bool,'same_named_subject':bool,
        'evidence':str,'confidence':'confidence'}

KINDS={'contract_body','contract_annex','coordinate_register_cover','coordinate_table',
       'waste_plan','safety_note','explanatory_note','equipment_schedule','graphic_cover',
       'heating_load','cooling_load','thermal_other','structural_calculation',
       'software_plot','project_cover','contents','other'}

def candidate(d):
    return bool(re.search(r'приложение|координат|отпадъц|БХТБП|безопасност|спецификация|графична\s+част|охладител|plan\s+view',d['right_heading'],re.I))

def _unguarded_proposal(f):
    validate_query_fields(f,SCHEMA)
    if any(f[k] not in KINDS for k in ('anchor_kind','left_kind','right_kind')):raise ValueError('Unknown artifact type')
    if f['confidence']<90:return None
    a,l,r=f['anchor_kind'],f['left_kind'],f['right_kind']
    if l=='contract_body' and r=='contract_annex' and f['right_explicit_contract_annex']:
        return False,'explicit_contract_attachment'
    if l=='coordinate_register_cover' and r=='coordinate_table':return False,'coordinate_register_cover_body'
    if l=='heating_load' and r=='cooling_load' and f['same_named_subject']:return False,'same_subject_hvac_outputs'
    # A separately named equipment table can have nonsequential or upside-down
    # rows. Its preceding safety narrative establishes that it is not continuing
    # another equipment table; row numbering is not a document-start requirement.
    if l=='safety_note' and r=='equipment_schedule' and re.search(r'спецификация',f['right_heading'],re.I):
        return True,'safety_note_to_named_equipment_schedule'
    # Interior software plots without an issued drawing title block stay with
    # the current calculation body. Preserve fresh report/drawing starts.
    if a==l=='structural_calculation' and r=='software_plot' and not f['right_fresh_start'] and not f['right_drawing_titleblock']:
        return False,'calculation_to_interior_software_plot'
    if not f['right_fresh_start']:return None
    if r=='safety_note' and a=='explanatory_note':return True,'separate_safety_note'
    if r=='waste_plan' and a in {'explanatory_note','safety_note'}:return True,'separate_waste_plan'
    if r=='equipment_schedule' and l in {'explanatory_note','safety_note'}:return True,'separate_equipment_schedule'
    if r=='graphic_cover' and l=='explanatory_note':return True,'separate_graphic_cover'
    return None

def combine(anchor,left,right):
    import page_artifact
    for facts in (anchor,left,right):page_artifact.validate(facts)
    def norm(s):return re.sub(r'\W+','',s.casefold())
    subject=norm(left['named_subject'])
    return {'anchor_kind':anchor['kind'],'left_kind':left['kind'],'right_kind':right['kind'],
            'anchor_heading':anchor['heading'],'left_heading':left['heading'],'right_heading':right['heading'],
            'right_fresh_start':right['fresh_start'],'right_explicit_contract_annex':right['explicit_contract_annex'],
            'right_drawing_titleblock':right['drawing_titleblock'],
            'same_named_subject':len(subject)>=8 and subject==norm(right['named_subject']),
            'confidence':min(anchor['confidence'],left['confidence'],right['confidence']),
            'evidence':'Independent single-image facts; no cross-image text attribution.'}


def contract_ids(heading):
    return {m.casefold().rstrip('.') for m in re.findall(r'\bдоговор\s*(?:№|номер|No\.?|N°)\s*([\w.-]+)',heading,re.I) if any(c.isdigit() for c in m)}

def abstention_reason(f,result):
    if not result:return None
    rule=result[1];heading=f['right_heading'].strip()
    if rule=='separate_safety_note':
        if re.match(r'^(?:\d+(?:\.\d+)*|[IVXLCDM]+)\s*[.)/]\s*',heading,re.I):
            return 'numbered_safety_section_needs_more_than_artifact_type'
    if rule=='separate_waste_plan':
        if f['left_kind']=='waste_plan' or re.match(r'^\d+\.\d+',heading):
            return 'waste_plan_continuation_not_an_independent_transition'
    if rule=='explicit_contract_attachment':
        parent=' '.join((f['anchor_heading'],f['left_heading']))
        if not re.search(r'\bдоговор\b',parent,re.I):
            return 'contract_annex_parent_not_identified_as_contract'
        parent_ids=contract_ids(parent);annex_ids=contract_ids(heading)
        if parent_ids and annex_ids and parent_ids!=annex_ids:
            return 'explicit_contract_identifier_conflict'
    return None


def proposal(f):
    result = _unguarded_proposal(f)
    return None if abstention_reason(f, result) else result
