"""Enforce the declared contiguous postal-receipt batch convention from read headings."""
import re

RECEIPT=re.compile(r'извести[ея]\s+за\s+доставяне|обратна\s+разписка',re.IGNORECASE)


def apply(decisions):
    result={p:dict(d) for p,d in decisions.items()}
    for page,data in decisions.items():
        if data['page_type_confidence']<90:continue
        left=bool(RECEIPT.search(data['left_heading']));right=bool(RECEIPT.search(data['right_heading']))
        following=decisions.get(page+1)
        next_receipt=following and following['page_type_confidence']>=90 and RECEIPT.search(following['right_heading'])
        rule=None;new=data['new_document']
        if left and right:new=False;rule='receipt_batch_continuation'
        elif right and not left and next_receipt:new=True;rule='first_receipt_of_batch'
        if rule:
            result[page].update(new_document=new,relationship='independent' if new else 'form_series',
                                filing_unit_rule=rule)
    return result
