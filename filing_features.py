"""Single-request filing decisions plus typed evidence for deterministic recovery."""
from filing_boundary_v5b import prompt as filing_prompt
from model_options import validate_query_fields
from page_profile import KINDS
from profile_policy_v4b import additions

SCHEMA={'left_heading':str,'right_heading':str,'left_kind':str,'right_kind':str,
        'left_columns':str,'right_columns':str,'right_first_row_label':str,
        'page_type_confidence':'confidence','relationship':str,'evidence':str,
        'new_document':bool,'confidence':'confidence'}


def prompt(variant,left,right):
    if variant!='features_v6':raise ValueError('Expected features_v6')
    parent=filing_prompt('filing_v5b',left,right).split('Return JSON in this order:')[0]
    return parent+'''
Before the relationship decision, extract the actual type of EACH image in its
supplied order. left_kind and right_kind must each be one of:
- review_sheet: municipal project review form with Обект, Част, становище/забележки,
  дата за връщане; not an application or a checklist of required documents;
- family_register: population report titled Списък/Опис на роднините, not an heirs
  certificate and not an ordinary family table continuing on another page;
- person_register: population report titled Пълни данни or equivalent personal
  record summary, not another page of the same family-register output;
- service_register: standalone administrative service/request activity table with
  incoming number, service, object, entered date, status, paid/price/due columns;
  not a construction cost schedule or bill of quantities;
- coordinate_table: standalone survey point list with X/Y or X/Y/Z/H coordinate
  columns, not an explanatory note, drawing legend or ordinary quantities;
- other: everything else or an unreadable/uncertain type.
For coordinate tables, copy left_columns, right_columns and right_first_row_label
literally; otherwise leave these fields empty. Do not assume numbering continues.
page_type_confidence describes how clearly BOTH types/fields can be read (0-100).
The document relationship decision still follows the filing instructions above.
Return JSON in this order:
{"left_heading":"literal heading or empty","right_heading":"literal heading or empty",
"left_kind":"one type","right_kind":"one type","left_columns":"literal columns or empty",
"right_columns":"literal columns or empty","right_first_row_label":"literal row label or empty",
"page_type_confidence":0-100,"relationship":"one relationship","evidence":"brief visible evidence",
"new_document":true/false,"confidence":0-100}.
'''


def decision(data):
    validate_query_fields(data,SCHEMA)
    if data['left_kind'] not in KINDS or data['right_kind'] not in KINDS:
        raise ValueError('Unknown page kind')
    raw_new=data.get('model_new_document',data['new_document'])
    raw_relation=data.get('model_relationship',data['relationship'])
    if raw_relation not in {'independent','continuation','attachment','section','form_series','uncertain'}:
        raise ValueError('Unknown relationship')
    if raw_new and raw_relation!='independent':raise ValueError('Contradictory raw boundary')
    left={'kind':data['left_kind'],'columns':data['left_columns'],'confidence':data['page_type_confidence']}
    right={'kind':data['right_kind'],'columns':data['right_columns'],'confidence':data['page_type_confidence'],
           'first_row_label':data['right_first_row_label']}
    recovery=additions(left,right) if not raw_new else None
    return {**data,'model_new_document':raw_new,'model_relationship':raw_relation,
            'new_document':bool(raw_new or recovery),'relationship':'independent' if raw_new or recovery else raw_relation,
            'feature_recovery':recovery}
