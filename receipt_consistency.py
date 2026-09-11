"""Isolated OCR bridge inside an already-established receipt batch; validated v1.

Only same physical page observations are compared. No filenames or labels enter
this rule. It neither creates a batch start nor attaches a receipt to a notice.
"""
from difflib import SequenceMatcher
import re
from filing_unit_policy import RECEIPT

def normalize(text):return re.sub(r'\s+',' ',text.casefold()).strip()
def nearby_reading(heading,alternate):
    return bool(RECEIPT.search(alternate)) and SequenceMatcher(None,normalize(heading),normalize(alternate)).ratio()>=0.90

def apply(decisions):
    result={p:dict(d) for p,d in decisions.items()}
    for page,d in decisions.items():
        previous=decisions.get(page-1);following=decisions.get(page+1)
        if not d['new_document'] or not previous or not following:continue
        if any(row['page_type_confidence']<90 for row in (previous,d,following)):continue
        if d['left_kind']!='other' or d['right_kind']!='other':continue
        # The neighbours each already read two receipt pages. This seam lies
        # inside that batch; adjacent independent instruments do not qualify.
        if not all(RECEIPT.search(row[side+'_heading']) for row in (previous,following) for side in ('left','right')):continue
        if not nearby_reading(d['left_heading'],previous['right_heading']):continue
        if not nearby_reading(d['right_heading'],following['left_heading']):continue
        result[page].update(new_document=False,relationship='form_series',filing_unit_rule='receipt_batch_same_page_ocr_bridge')
    return result
