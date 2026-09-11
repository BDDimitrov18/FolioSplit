"""Select semantic verification windows; no labels, filenames or page constants."""
import re

def select(decisions):
    starts=[1]+[p for p,d in sorted(decisions.items()) if d['new_document']]
    rows=[]
    for page,d in sorted(decisions.items()):
        cut=d['new_document'];headings=d['left_heading']+' '+d['right_heading'];reasons=[]
        if cut and re.search(r'доклад|оценка.*съответств|статическо.*обследване|apostille|апостил|пълномощно|letter of attorney',headings,re.I):reasons.append('report_or_legal')
        if cut and d['right_kind']=='review_sheet':reasons.append('review_sheet')
        if not cut and re.search(r'нормативна',d['right_heading'],re.I):reasons.append('regulatory_section')
        if cut and re.search(r'топлинни загуби|охладителен товар|потребна топлинна мощност',d['right_heading'],re.I):reasons.append('thermal')
        if not reasons:continue
        anchor=max(p for p in starts if p<page);context={anchor,page-1,page}
        if 'review_sheet' in reasons and page>=3:context.add(page-2)
        rows.append(dict(anchor_page=anchor,right_page=page,base_cut=cut,reasons=reasons,context_pages=sorted(context),
                         legal=bool('report_or_legal' in reasons and re.search(r'apostille|апостил|пълномощно|letter of attorney',headings,re.I))))
    return rows
