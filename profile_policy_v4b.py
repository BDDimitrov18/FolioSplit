"""Development refinement: recognize H as the height column in survey outputs."""
import re
from page_profile import additions as original_additions


def additions(left,right):
    def normalize(row):
        result=dict(row)
        # Preserve evidence verbatim; normalize a copy only for comparing schemas.
        result['columns']=re.sub(r'(?<!\w)[hн](?!\w)','Z',row.get('columns',''),flags=re.IGNORECASE)
        return result
    return original_additions(normalize(left),normalize(right))
