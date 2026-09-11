"""Single-image artifact extraction, avoiding cross-image attribution."""
from model_options import validate_query_fields
SCHEMA={'kind':str,'heading':str,'fresh_start':bool,'explicit_contract_annex':bool,
        'drawing_titleblock':bool,'named_subject':str,'evidence':str,'confidence':'confidence'}
KINDS={'contract_body','contract_annex','coordinate_register_cover','coordinate_table',
       'waste_plan','safety_note','explanatory_note','equipment_schedule','graphic_cover',
       'heating_load','cooling_load','thermal_other','structural_calculation',
       'software_plot','project_cover','contents','other'}
def prompt(page):
    return f'''Read this ONE image of source page {page}. Extract its visible facts.
Do not infer anything about other pages or whether a document should be split.
Choose kind: contract_body, contract_annex, coordinate_register_cover, coordinate_table,
waste_plan, safety_note, explanatory_note, equipment_schedule, graphic_cover,
heating_load, cooling_load, thermal_other, structural_calculation, software_plot,
project_cover, contents, other.
contract_body contains contractual articles/parties/signatures. contract_annex must
explicitly say it is an annex TO a contract; a generic technical assignment does not.
coordinate_register_cover is a title sheet for a point-coordinate register, without
coordinate rows; coordinate_table contains point numbers and X/Y/Z coordinate columns.
waste_plan is a separately headed waste-management section/plan, including an explicit
exemption explanation under that heading; not a contents entry merely listing it.
safety_note is an explanatory note or plan for workplace safety/health (БХТБП,
безопасност и здраве) or fire safety. Ordinary design narrative is explanatory_note.
equipment_schedule is a table of equipment names/counts, not a price invoice/index.
graphic_cover is a standalone ГРАФИЧНА ЧАСТ title sheet, not an actual drawing.
heating_load and cooling_load contain numeric HVAC heat/cooling load output;
energy-envelope calculations and other thermal computations are thermal_other.
structural_calculation contains actual numeric structural checks; software_plot
is engineering software visualization. drawing_titleblock requires an actual issued
drawing title block/sheet number; a stamp or program footer alone does not suffice.
fresh_start requires an actual heading plus introductory text, initial table entries,
or a standalone title sheet. Repeated headers/continuing rows/interior results are false.
Copy heading literally. named_subject is a literal room/building/project name printed
on this page, empty if absent; do not infer it from a logo, signature or general topic.
Use evidence <=25 words and confidence 0-100. Return JSON fields:
kind,heading,fresh_start,explicit_contract_annex,drawing_titleblock,named_subject,evidence,confidence.
'''
def validate(f):
    validate_query_fields(f,SCHEMA)
    if f['kind'] not in KINDS:raise ValueError('Unknown page kind')
    return f
