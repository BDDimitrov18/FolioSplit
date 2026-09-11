"""Recover a wrapped company-name suffix only from independently visible crop text."""
import re
import legal_identity

def words(s):return re.findall(r'\w+',s.casefold())
def same(a,b,key):return words(a[key])==words(b[key]) and bool(words(a[key]))
def prefix(a,b):
    x,y=words(a),words(b)
    return bool(x) and sum(map(len,x))>=7 and x==y[:len(x)]

def needed(full,left,right):
    if min(f['confidence'] for f in (full,left,right))<90:return False
    if (full['kind'],left['kind'],right['kind'])!=('notarial_signature_certificate','apostille','power_of_attorney'):return False
    if legal_identity.proposal(full,left,right):return False
    return (full['certifies_attached_power_of_attorney']
            and same(full,right,'principal_name') and same(full,right,'principal_birth_date')
            and prefix(full['principal_company_name'],right['principal_company_name']))

def proposal(full,left,right,crop):
    if not needed(full,left,right):return None
    if not same(full,crop,'principal_name') or not same(full,crop,'principal_birth_date'):return None
    if not prefix(full['principal_company_name'],crop['principal_company_name']):return None
    result=legal_identity.proposal(crop,left,right)
    return (False,'certified_attachment_with_corroborated_company_crop') if result else None
