"""Development filing refinement for catalogs and continued contents sheets."""
from filing_boundary import prompt as original_prompt


def prompt(variant,left,right):
    if variant!='filing_v5b':raise ValueError('Expected filing_v5b')
    text=original_prompt('filing_v5',left,right)
    before='''- a contents/index page followed by its explicitly listed explanatory note within
  the same discipline. A cover is not an index. A heading alone does not prove a
  separate output when it is clearly the next section of an ongoing document.'''
    after='''- equipment/product catalog compilations: consecutively numbered product entries
  such as 1.1, 1.2, 1.3, 2.1, 2.2 stay together with their specifications and photos.
  A different lamp, breaker, starter or other product model is another catalog item,
  not a new document. Preserve a separately issued certificate/letter or clearly
  independent manufacturer document outside that continuing numbered compilation;
- a contents/index page OR continued contents sheet followed by the explanatory
  text of the same discipline. Continued contents can have no СЪДЪРЖАНИЕ heading:
  short numbered section/drawing titles without explanatory prose identify it.
  The earlier explanatory-note entry can be on the preceding contents sheet.
  A technical narrative/list of specifications is not contents, and a cover is not
  an index. A heading alone does not prove a separate output within an ongoing doc.'''
    if before not in text:raise ValueError('Parent filing prompt changed')
    return text.replace(before,after)
