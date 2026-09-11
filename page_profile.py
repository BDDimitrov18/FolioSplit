"""Single-page extraction for experimental recovery of distinct archive outputs."""
from model_options import validate_query_fields

KINDS = {'review_sheet', 'family_register', 'person_register', 'service_register',
         'coordinate_table', 'other'}
SCHEMA = {'heading': str, 'kind': str, 'columns': str, 'first_row_label': str,
          'last_row_label': str, 'evidence': str, 'confidence': 'confidence'}


def prompt(variant, left, right):
    if variant != 'profile_v4' or type(right) is not int or right < 1:
        raise ValueError('Expected profile_v4 and a positive page')
    return f'''Read only the attached scanned page {right}. Extract what THIS page
actually contains. Do not infer its content from neighboring pages or from a larger
project. Read sideways text if necessary. Do not invent cropped or unreadable text.
Select kind from these exact values:
- review_sheet: municipal project review form with repeated Обект, Част,
  становище/забележки and дата за връщане fields; NOT an application/checklist.
- family_register: population-register report explicitly titled Списък/Опис на
  роднините or similar, with the person's family relations. NOT an heirs certificate.
- person_register: population-register report explicitly titled Пълни данни or
  equivalent personal-record summary; NOT a continuation of a family table.
- service_register: administrative service/request activity report with columns
  such as incoming number, service, object, entered date, status, paid, price/due.
  NOT a construction bill of quantities or contract cost schedule.
- coordinate_table: standalone list of surveyed points and their X/Y or X/Y/Z
  coordinates. NOT a drawing legend, ordinary quantities, or narrative note.
- other: all other pages or when the type cannot be reliably read.
heading: transcribe the visible document heading, or empty if none. For a table,
columns: transcribe its column labels in order; first_row_label and last_row_label:
transcribe the point/row label of the first and last data row, or empty if unclear.
evidence: one short sentence identifying the visible features supporting the kind.
Return JSON {{"heading":"literal heading", "kind":"one kind", "columns":"literal columns",
"first_row_label":"literal label", "last_row_label":"literal label",
"evidence":"brief visible evidence", "confidence":0-100}}.
'''


def decision(data):
    validate_query_fields(data, SCHEMA)
    if data['kind'] not in KINDS: raise ValueError('Unknown page profile kind')
    return {**data, 'new_document':True, 'relationship':'independent',
            'left_heading':'', 'right_heading':data['heading']}


def additions(left, right):
    """Return a named recovery reason, never a label-dependent page number."""
    if right['confidence'] < 90: return None
    lk, rk = left['kind'], right['kind']
    if rk == 'review_sheet' and lk != 'review_sheet': return 'first_review'
    if rk in {'family_register','person_register','service_register'} and lk != rk:
        return 'distinct_register'
    if rk == 'coordinate_table' and lk != rk: return 'first_coordinates'
    if rk == lk == 'coordinate_table':
        # A different column schema plus an explicit row restart is evidence of a
        # separate survey output. A repeated heading alone is insufficient.
        def cols(s):
            import re
            normalized = s.lower().translate(str.maketrans({'х':'x','у':'y','з':'z'}))
            return re.findall(r'(?<!\w)[xyz](?!\w)',normalized)
        lc, rc = cols(left['columns']), cols(right['columns'])
        first = right['first_row_label'].strip().rstrip('.)')
        if lc and rc and lc != rc and first in {'1','01','001'}:
            return 'new_coordinate_output'
    return None
