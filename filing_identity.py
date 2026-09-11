"""Focused report/municipal-form identity; independently read each page."""
from model_options import validate_query_fields
SCHEMA={k:str for k in ('kind','regulated_plot','cadastral_id','quarter','subproject','subject','heading','evidence')}
SCHEMA.update(object_field=bool,part_field=bool,return_date_field=bool,confidence='confidence')
def prompt(page):
    return '''Read this ONE page independently. Identify its visible document form and project references.
kind must be assessment_report_cover, assessment_report_body, review_sheet,
signature_reverse, or other.
assessment_report is a professional conformity/compliance assessment (оценка за
съответствие, доклад) of a construction project. Distinguish title-only cover from body.
review_sheet is a municipal project review/approval form, including a form whose fields
are mostly HANDWRITTEN. Faint printed dotted-line labels 'Обект', 'Част', 'Дата за връщане'
count even when the handwriting is hard to read. A handwritten form is not a blank sheet.
signature_reverse is a mostly empty reverse sheet with a closing note/signature but NO form fields.
object_field,part_field,return_date_field indicate those actual printed form labels.
regulated_plot is the FULL regulated land plot reference after УПИ (or its equivalent
Roman numeral plus plot number in an ОБЕКТ block), including Roman numeral and digits.
cadastral_id is the separate dotted ПИ identifier. Never replace one with the other.
quarter is the literal quarter number after кв. subproject is the literal ПОДОБЕКТ
(e.g. a building number). subject is the printed project title. Copy exact strings,
leave absent/unreadable fields empty. Preserve handwritten corrections as visible;
do not resolve inconsistent identifiers or infer identity from another page.
Return JSON kind,regulated_plot,cadastral_id,quarter,subproject,subject,heading,
object_field,part_field,return_date_field,evidence,confidence.
evidence <=20 words, confidence 0-100. Do not decide document boundaries.
'''
def validate(f):
    validate_query_fields(f,SCHEMA)
    if f['kind'] not in {'assessment_report_cover','assessment_report_body','review_sheet','signature_reverse','other'}:raise ValueError('Unknown filing kind')
    return f

def proposal(anchor,left,right,earlier=None):
    import re
    def norm(s):return re.sub(r'\W+','',s.casefold())
    def same(a,b,k,n):x=norm(a[k]);return len(x)>=n and x==norm(b[k])
    if min(left['confidence'],right['confidence'])<90:return None
    if left['kind']=='assessment_report_cover' and right['kind']=='assessment_report_body':
        if all(same(left,right,k,n) for k,n in [('regulated_plot',6),('quarter',1),('subproject',3)]):
            return False,'assessment_cover_body_same_regulated_plot_and_subproject'
    if earlier and earlier['confidence']>=90 and earlier['kind']==right['kind']=='review_sheet' and left['kind']=='signature_reverse':
        fields=('object_field','part_field','return_date_field')
        if not all(earlier[k] and right[k] for k in fields):return None
        for key in ('regulated_plot','cadastral_id','subproject'):
            if earlier[key] and right[key] and norm(earlier[key])!=norm(right[key]):return None
        return False,'same_review_form_across_signature_reverse'
    return None
