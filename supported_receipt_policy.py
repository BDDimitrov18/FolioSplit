"""Keep a single supporting postal receipt with a preceding municipal notice."""
import re
from filing_unit_policy import RECEIPT
NOTICE = re.compile(r'^\s*(?:съобщение|уведомително\s+писмо)\b', re.I)


def apply(decisions):
    result = {p: dict(d) for p, d in decisions.items()}
    for page, data in decisions.items():
        if (not data['new_document'] or data['page_type_confidence'] < 90
                or not NOTICE.search(data['left_heading'])
                or not RECEIPT.search(data['right_heading'])):
            continue
        following = decisions.get(page + 1)
        if following and (following['page_type_confidence'] < 90
                          or RECEIPT.search(following['right_heading'])):
            continue
        result[page].update(new_document=False, relationship='attachment',
                            filing_unit_rule='single_receipt_supports_notice')
    return result
