"""Direct boundary experiment using archive filing units rather than project bundles."""
from pair_boundary import SCHEMA, decision


def prompt(variant, left, right):
    if variant != 'filing_v5' or type(left) is not int or left < 1 or right != left+1:
        raise ValueError('Expected filing_v5 and adjacent pages')
    return f'''Read the two scanned Bulgarian archive pages in order: page {left},
then page {right}. Decide whether a separately filed DOCUMENT begins on page {right}.
Transcribe each page's actual heading before deciding. Do not describe one image
using text from the other. A shared project, person, stamp, or issuer is not enough
to merge two independently introduced documents. Do not invent unreadable text.

The filing unit is smaller than an overall construction project or application
bundle. These can each be separately filed, even when referred to as attachments:
- a project cover followed by the designer's qualification certificate, insurance
  policy, contract, permit or letter: each new instrument starts a document;
- a standalone explanatory note, calculation output, bill of quantities, design
  drawing or survey coordinate output with its own introduction/title;
- a distribution list РАЗПИСЕН ЛИСТ, or a distinct population-register report such
  as Списък на роднините versus Пълни данни, even for the same person;
- a standalone administrative service/requests register after a technical note;
- the FIRST municipal review sheet after an application or another document.
A reference saying 'attached' does not by itself cancel these independent starts.

Keep actual continuations together:
- consecutive text/table pages of the same output, including repeated column
  headers and continuing rows. A new independently titled coordinate output with
  changed X/Y/Z columns and a row restart can be separate;
- closing-only signatures/stamps/notarial certification completing the preceding
  instrument; a signed complete one-page document is not a closing-only page;
- BOTH pages being municipal review forms with Обект, Част, становище/забележки,
  дата за връщане for the same project: different disciplines/reviewers are entries;
- postal ИЗВЕСТИЕ ЗА ДОСТАВЯНЕ or ОБРАТНА РАЗПИСКА supporting the preceding letter,
  and consecutive receipts from the same dispatch. РАЗПИСЕН ЛИСТ is different;
- ТЪРГОВСКИ УСЛОВИЯ belonging to the preceding contract;
- a contents/index page followed by its explicitly listed explanatory note within
  the same discipline. A cover is not an index. A heading alone does not prove a
  separate output when it is clearly the next section of an ongoing document.

Use relationship independent when a separate filing unit begins, even if it
supports the same project. Otherwise use continuation, attachment, section,
form_series, or uncertain. new_document must be true only for independent.
When uncertain, explain the missing visible evidence briefly.
Return JSON in this order:
{{"left_heading":"literal heading or empty", "right_heading":"literal heading or empty",
"relationship":"one category", "evidence":"one brief sentence of visible evidence",
"new_document":true/false, "confidence":0-100}}.
'''
