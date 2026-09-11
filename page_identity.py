"""Independent literal page evidence; no boundary decisions or ground truth."""
from model_options import validate_query_fields
SCHEMA = {k: str for k in ('kind','heading','project_id','project_name','report_id',
    'signed_document_date','principal_birth_date','principal_company_id','printed_page','printed_total','evidence')}
SCHEMA.update(fresh_start=bool, explicit_certifies_poa=bool, confidence='confidence')
KINDS=set('project_cover contents assessment_report_cover assessment_report_body notarial_signature_certificate apostille power_of_attorney professional_certificate insurance review_sheet signature_note technical_assignment work_quantity_table materials_table regulatory_list waste_plan heating_output cooling_output other_thermal structural_report_cover structural_calculation other'.split())
def prompt(page):
    return '''Read this ONE page image independently. Extract ONLY visible facts, never whether to split documents.
Choose kind: project_cover, contents, assessment_report_cover, assessment_report_body,
notarial_signature_certificate, apostille, power_of_attorney, professional_certificate,
insurance, review_sheet, signature_note, technical_assignment, work_quantity_table,
materials_table, regulatory_list, waste_plan, heating_output, cooling_output,
other_thermal, structural_report_cover, structural_calculation, other.
assessment_report is a professional assessment of conformity/compliance of a construction
project (оценка за съответствие, доклад); distinguish its title-only cover from substantive text.
A municipal review_sheet has a printed project approval/review form, not a drawing title block.
A signature_note is a largely blank reverse sheet with a closing handwritten note/signature.
notarial_signature_certificate certifies someone's signature; explicit_certifies_poa is true
ONLY if visible text actually identifies the certified document as a power of attorney.
heating_output uses winter temperatures/heating loss; cooling_output uses summer temperatures/cooling loads.
regulatory_list is a section listing legislation. materials_table lists construction materials;
work_quantity_table lists construction tasks. Do not treat a contents entry as the actual section.
Copy heading literally. Copy project_id as the literal plot/cadastral reference of the subject
project, project_name as a literal printed building/project/room name, report_id as the literal
identifier of this report. Leave absent strings EMPTY; do not guess or use logo/author names.
For legal pages only, copy signed_document_date, principal_birth_date, principal_company_id
ONLY when explicitly printed as the document signing date and principal's birth date/company ID.
Do not mistake registration dates or notary license IDs for these fields.
printed_page and printed_total are printed page numbers of THIS source document, not image numbering.
Use digit strings if explicit (e.g. 7 and 18 from '7 от 18'); empty if absent or unreadable.
fresh_start means a title sheet or actual heading with introductory material, not a repeated header.
evidence <=20 words, confidence 0-100. Return JSON fields:
kind,heading,fresh_start,project_id,project_name,report_id,signed_document_date,
principal_birth_date,principal_company_id,explicit_certifies_poa,printed_page,printed_total,evidence,confidence.
'''
def validate(f):
    validate_query_fields(f,SCHEMA)
    if f['kind'] not in KINDS:raise ValueError('Unknown page kind')
    for key in ('printed_page','printed_total'):
        if f[key] and not f[key].isdigit():raise ValueError('Printed pagination must be digits or empty')
    return f
