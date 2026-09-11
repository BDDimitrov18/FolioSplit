"""Source-bound OCR checkpoints for the narrow report identity corroboration."""
import json,time
import report_ocr_policy
from production_state import atomic_json,source_identity

def read(pdf,page,*,pipeline,directory,source,settings,rotations,dpi):
    path=directory/'report_ocr'/f'{page:04}.json'
    identity={'source':source,'settings':settings,'page':page,'modes':[6,11],'language':'eng'}
    old=json.loads(path.read_text()) if path.exists() else None
    if old and old['identity']!=identity:raise ValueError('Report OCR cache identity mismatch')
    if old and old['status']=='complete':
        if source_identity(pdf)!=source:raise ValueError('Source changed during report OCR')
        return old,True
    tick=time.monotonic();record={'identity':identity,'model_usage':None,'attempts':old.get('attempts',0)+1 if old else 1,
                                'history':[*old.get('history',[]),{k:v for k,v in old.items() if k not in ('identity','history')}] if old else []}
    try:
        image=pipeline._load_page(pdf,page,dpi);angle=rotations.get(page,0)
        if angle:image=image.rotate(angle,expand=True)
        rows=report_ocr_policy.query(image);record.update(results=rows,rotation_ccw=angle)
        if any(r['error'] for r in rows):raise RuntimeError('Report OCR execution failed; see checkpoint errors')
        if source_identity(pdf)!=source:raise ValueError('Source changed during report OCR')
        record['status']='complete'
    except BaseException as exc:record.update(status='failed',error=str(exc));raise
    finally:record['seconds']=time.monotonic()-tick;atomic_json(path,record)
    return record,False
