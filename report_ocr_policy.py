"""Corroborate a regulated-plot transcription with two OCR modes and a VLM crop."""
import re

def norm(s):
    return re.sub(r'\W+','',s.casefold().translate(str.maketrans({'х':'x','і':'i','ι':'i','ⅴ':'v'})))

def numeric_reference(text):
    found=re.findall(r'(?<!\d)\d{5,}(?!\d)',text)
    return found[0] if len(found)==1 else None

def needed(left,right):
    if min(left['confidence'],right['confidence'])<90:return None
    if (left['kind'],right['kind'])!=('assessment_report_cover','assessment_report_body'):return None
    if not all(left[k] and norm(left[k])==norm(right[k]) for k in ('quarter','subproject')):return None
    number=numeric_reference(left['regulated_plot'])
    if number and number==numeric_reference(right['regulated_plot']) and norm(left['regulated_plot'])!=norm(right['regulated_plot']):return number
    return None

def extract(text,number):
    text=text.upper().translate(str.maketrans({'Х':'X','І':'I','Ι':'I','Ⅴ':'V'}))
    return {roman+digits for roman,digits in re.findall(r'(?<![A-Z])([IVXLCDM]{1,8})\s*[-–,]?\s*(\d{5,})(?!\d)',text) if digits==number}

def consensus(texts,number):
    sets=[extract(text,number) for text in texts]
    return next(iter(sets[0])) if len(sets)==2 and len(sets[0])==1 and sets[0]==sets[1] else None

def proposal(left,right,left_crop,right_crop,left_texts,right_texts):
    number=needed(left,right)
    if not number or min(left_crop['confidence'],right_crop['confidence'])<90:return None
    first,last=consensus(left_texts,number),consensus(right_texts,number)
    if not first or first!=last:return None
    if norm(left_crop['regulated_plot'])!=norm(first) or norm(right_crop['regulated_plot'])!=norm(last):return None
    for full,crop in ((left,left_crop),(right,right_crop)):
        if any(norm(full[k])!=norm(crop[k]) for k in ('quarter','subproject')):return None
    return False,'report_cover_body_with_ocr_and_crop_consensus'

def query(image):
    import subprocess,tempfile
    from pathlib import Path
    rows=[]
    with tempfile.TemporaryDirectory(prefix='report-ocr-') as tmp:
        path=Path(tmp)/'page.png';image.save(path)
        for mode in (6,11):
            try:
                result=subprocess.run(['tesseract',str(path),'stdout','-l','eng','--psm',str(mode)],capture_output=True,text=True,timeout=30)
                rows.append(dict(mode=mode,text=result.stdout if result.returncode==0 else '',error=result.stderr if result.returncode else None))
            except (OSError,subprocess.TimeoutExpired) as exc:rows.append(dict(mode=mode,text='',error=str(exc)))
    return rows
