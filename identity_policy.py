"""Frozen hypotheses based on independently transcribed page evidence."""
import re

def norm(value):
    return re.sub(r'\W+', '', value.casefold())

def same(a,b,key,minimum=4):
    x=norm(a.get(key,''));return len(x)>=minimum and x==norm(b.get(key,''))

def compatible(a,b):
    return all(not(a.get(k) and b.get(k)) or norm(a[k])==norm(b[k])
               for k in ('project_id','project_name','report_id'))

def roman_plot_refs(value):
    """Keep explicit Roman plot labels when comparing numeric project references."""
    import unicodedata
    text=unicodedata.normalize('NFKC',value).upper().translate(str.maketrans({'Х':'X','І':'I'}))
    text=re.sub(r'(?<!\w)(?:УПИ|UPI)\s*[:\-]?\s*',' ',text)
    refs={}
    for roman,number in re.findall(r'(?<!\w)([IVXLCDM](?:\s*[IVXLCDM])*)\s*[-–—]?\s*(\d{5,}(?:\.\d+)*)(?!\d)',text):
        refs.setdefault(number,set()).add(re.sub(r'\s+','',roman))
    return refs


def conflicting_roman_plots(a,b):
    left=roman_plot_refs(a.get('project_id',''));right=roman_plot_refs(b.get('project_id',''))
    return any(left[number]!=right[number] for number in left.keys() & right.keys())


def shared_project(a,b):
    if conflicting_roman_plots(a,b):return False
    def identifiers(s):return set(re.findall(r'(?<!\d)\d{5,}(?:\.\d+)*',s))
    left,right=identifiers(a.get('project_id','')),identifiers(b.get('project_id',''))
    if left and right:
        if left!=right:return False
        if a.get('report_id') and b.get('report_id') and not same(a,b,'report_id'):return False
        x,y=norm(a.get('project_name','')),norm(b.get('project_name',''))
        return not(x and y) or x==y or (min(len(x),len(y))>=15 and (x.startswith(y) or y.startswith(x)))
    return compatible(a,b) and any(same(a,b,k,8 if k=='project_name' else 4)
                                 for k in ('project_id','project_name','report_id'))

def proposal(anchor,left,right,earlier=None):
    if min(x['confidence'] for x in (anchor,left,right))<90:return None
    a,l,r=anchor['kind'],left['kind'],right['kind']
    if a=='notarial_signature_certificate' and l=='apostille' and r=='power_of_attorney':
        keys=('signed_document_date','principal_birth_date','principal_company_id')
        matches=sum(same(anchor,right,k,6) for k in keys)
        conflict=any(anchor.get(k) and right.get(k) and norm(anchor[k])!=norm(right[k]) for k in keys)
        if matches>=2 and not conflict:return False,'certified_power_of_attorney_bundle'
    if l=='assessment_report_cover' and r=='assessment_report_body' and shared_project(left,right):
        return False,'assessment_report_cover_body'
    thermal={'heating_output','cooling_output','other_thermal'}
    left_temperature_table=l in thermal or (l=='other' and bool(re.search(r'θint\s*=\s*-?\d+.*θe\s*=\s*-?\d+',left.get('heading',''),re.I)))
    if a in thermal and left_temperature_table and r in thermal and shared_project(anchor,right) and compatible(left,right):
        return False,'same_project_seasonal_outputs'
    if l=='waste_plan' and r=='regulatory_list' and right['fresh_start']:
        lp,rp=left.get('printed_page',''),right.get('printed_page','')
        total=left.get('printed_total','')
        if lp and rp and total and total==right.get('printed_total') and int(rp)<int(lp)<=int(total):
            return True,'reordered_regulatory_section_after_waste_plan'
    if earlier and earlier['confidence']>=90 and earlier['kind']=='review_sheet' and l=='signature_note' and r=='review_sheet' and shared_project(earlier,right):
        return False,'review_forms_across_signature_reverse'
    return None
