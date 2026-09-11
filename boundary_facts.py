"""Typed facts for narrowly scoped missed-start recovery; no model filing verdict."""
import re
from model_options import validate_query_fields

ROLES={'project_cover','cover_continuation','contents','narrative','calculation_output',
       'thermal_output','company_certificate','personnel_list','other'}
SCHEMA={'left_role':str,'right_role':str,'right_first_page':bool,
        'left_evidence':str,'right_evidence':str,'confidence':'confidence'}


def candidate_reason(data):
    if data['new_document']:return None
    text=' '.join(str(data.get(k,'')) for k in ('left_heading','right_heading','evidence'))
    if re.search(r'cover|title.page|статическ.*изчислен|^проект\b',text,re.I):return 'possible_cover'
    if re.search(r'thermal|energy|топло|термич|енерги',text,re.I):return 'possible_thermal_start'
    if re.search(r'персонал|personnel|staff.list',text,re.I):return 'possible_personnel_list'
    return None


def prompt(left,right):
    return f'''Extract visible page facts only. INPUT IMAGE 1 is source page {left};
INPUT IMAGE 2 is source page {right}. Do not decide whether the archive should
split them and do not infer a role from their relationship. Read each image.

Choose left_role and right_role independently from:
- project_cover: title-only front sheet with project, discipline, designer, phase
  and date fields; no substantive explanation, computations or contents list;
- cover_continuation: reverse/additional sheet listing the cover's designers or
  signatures, without independently issued certificate text;
- contents: index or continued short list of section/drawing titles;
- narrative: prose explanation, conclusions or method descriptions, possibly
  referring to attached results; not the attached numeric output itself;
- calculation_output: numerical structural/computational report, input-data
  tables or computed results, not a cover or narrative;
- thermal_output: numerical heat/energy calculation tables or indicators such as
  U/R values, condensation or energy consumption; not prose merely mentioning them;
- company_certificate: issued company qualification or registration certificate;
- personnel_list: separately introduced certified list/register of personnel,
  not a table continuing on another page;
- other: another type, unclear or unreadable.

right_first_page is true only when IMAGE 2 visibly opens its own output: introductory
heading plus initial data/parameters or a clear first-page/row numbering restart.
It is false for continuing table rows, numbered interior subsections, ongoing
results, or cover-continuation text. Being attached to the preceding report does
not change these physical page facts. Do not infer first-page status from a stamp.
Provide <=20 words of visible evidence per image and confidence for the facts.
Return JSON only:
{{"left_role":"one role","right_role":"one role","right_first_page":true/false,
"left_evidence":"visible evidence","right_evidence":"visible evidence","confidence":0-100}}.
'''


def recovery(data):
    validate_query_fields(data,SCHEMA)
    if data['left_role'] not in ROLES or data['right_role'] not in ROLES:raise ValueError('Unknown fact role')
    if data['confidence']<90:return None
    left,right=data['left_role'],data['right_role']
    if left=='project_cover' and right=='contents':return 'cover_to_contents'
    if not data['right_first_page']:return None
    if left=='project_cover' and right in {'narrative','calculation_output','thermal_output'}:return 'cover_to_body'
    if left=='narrative' and right=='thermal_output':return 'narrative_to_thermal_output'
    if left=='company_certificate' and right=='personnel_list':return 'certificate_to_personnel_list'
    return None


def recover_decision(base,facts):
    rule=recovery(facts)
    if not rule:return {**base,'fact_recovery':None}
    return {**base,'new_document':True,'relationship':'independent',
            'confidence':facts['confidence'],'fact_recovery':rule}
