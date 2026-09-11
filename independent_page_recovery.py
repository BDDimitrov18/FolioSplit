"""Shared single-image inference with source/settings-bound restartable checkpoints."""
import json,time
from model_options import usage_snapshot,usage_delta
from production_state import atomic_json,source_identity

def read(pdf,requests,module,stage,bundle,dpi,logger,*,pipeline,directory,source,settings,rotations):
    facts={};records=[];cached=0
    for page,crop in sorted(set(requests)):
        suffix=f'_{crop}' if crop else '';path=directory/stage/f'{page:04}{suffix}.json'
        identity={'source':source,'settings':settings,'page':page,'single_image':True,'crop':crop}
        old=json.loads(path.read_text()) if path.exists() else None
        if old and old['identity']!=identity:raise ValueError('Independent page cache identity mismatch')
        if old and old['status']=='complete':
            facts[(page,crop)]=module.validate(old['facts']);records.append(old);cached+=1;continue
        before=usage_snapshot(bundle[0]);tick=time.monotonic()
        record={'identity':identity,'attempts':old.get('attempts',0)+1 if old else 1,
                'history':[*old.get('history',[]),{k:v for k,v in old.items() if k not in ('identity','history')}] if old else []}
        try:
            image=pipeline._load_page(pdf,page,dpi);angle=rotations.get(page,0)
            if angle:image=image.rotate(angle,expand=True)
            record['rotation_ccw']=angle
            if crop=='upper':image=image.crop((0,0,image.width,round(image.height*0.6)))
            elif crop=='lower':image=image.crop((0,round(image.height*0.4),image.width,image.height))
            elif crop=='wide':image=image.crop((0,0,image.width,round(image.height*0.72)))
            elif crop:raise ValueError('Unknown page crop')
            client=bundle[0];has_labels=hasattr(client,'image_labels');old_labels=getattr(client,'image_labels',None)
            if has_labels:client.image_labels=False
            try:raw=pipeline._infer(module.prompt(page),[image],*bundle,logger,max_tokens=600,response_schema=module.SCHEMA)
            finally:
                if has_labels:client.image_labels=old_labels
            facts[(page,crop)]=module.validate(json.loads(pipeline.clean_response(raw)))
            record.update(status='complete',facts=facts[(page,crop)],raw_final=raw)
            logger.info('%s %s p%d%s kind=%s',stage.upper(),pdf.name,page,suffix,facts[(page,crop)]['kind'])
        except BaseException as exc:record.update(status='failed',error=str(exc));raise
        finally:
            record.update(seconds=time.monotonic()-tick,model_usage=usage_delta(before,usage_snapshot(bundle[0])))
            atomic_json(path,record);records.append(record)
    if source_identity(pdf)!=source:raise ValueError('Source changed during independent page verification')
    return facts,records,cached
