"""Focused literal identity transcription for signed legal attachments."""
from model_options import validate_query_fields
SCHEMA={k:str for k in ('kind','principal_name','principal_birth_date','principal_company_name','principal_company_id','attachment_quote','evidence')}
SCHEMA.update(certifies_attached_power_of_attorney=bool,confidence='confidence')
def prompt(page):
    return '''Read this ONE scanned page independently. Extract visible legal identity facts.
kind must be notarial_signature_certificate, power_of_attorney, apostille, or other.
principal_name is the person whose signature is certified or who GRANTS authority;
never substitute the notary or an authorized recipient. Copy their full name exactly.
principal_birth_date is that same person's birth date. principal_company_name and
principal_company_id identify the company they represent. Copy the COMPLETE company name,
including digits/numbers even if they wrap onto the next line. Exclude legal-form
suffixes such as ЕООД, ООД, АД from principal_company_name. Preserve literal digits,
including apparent mistakes; never correct company identifiers.
When Bulgarian text is present, use the Bulgarian spelling of names/company names.
Do not translate or transliterate. Leave absent text empty.
certifies_attached_power_of_attorney is true ONLY if the certificate explicitly says
that the certified signature is on an attached power of attorney. Read all language
blocks, especially any Bulgarian translation. Copy the exact supporting short phrase
into attachment_quote (otherwise empty). A generic signature certificate is insufficient.
Return JSON kind,principal_name,principal_birth_date,principal_company_name,
principal_company_id,certifies_attached_power_of_attorney,attachment_quote,evidence,confidence.
evidence <=15 words, confidence 0-100. No document-splitting decision.
'''
def validate(f):
    validate_query_fields(f,SCHEMA)
    if f['kind'] not in {'notarial_signature_certificate','power_of_attorney','apostille','other'}:raise ValueError('Unknown legal kind')
    return f

def proposal(certificate,apostille,attorney):
    import re
    def norm(s):return re.sub(r'\W+','',s.casefold())
    if min(f['confidence'] for f in (certificate,apostille,attorney))<90:return None
    if (certificate['kind'],apostille['kind'],attorney['kind'])!=('notarial_signature_certificate','apostille','power_of_attorney'):return None
    if not certificate['certifies_attached_power_of_attorney'] or not re.search(r'пълномощ|power of attorney',certificate['attachment_quote'],re.I):return None
    for key,minimum in [('principal_name',12),('principal_birth_date',8),('principal_company_name',6)]:
        a=norm(certificate[key]);b=norm(attorney[key])
        if len(a)<minimum or a!=b:return None
    return False,'explicit_certified_attachment_same_principal'
