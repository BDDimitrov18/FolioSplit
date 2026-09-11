"""Terminal artifact verification with source-bound single-page checkpoints."""
import json,time
import artifact_policy,page_artifact
from model_options import usage_snapshot,usage_delta,summarize_usage
from production_state import atomic_json,source_identity

def recover(pdf,total,bundle,dpi,logger,*,pipeline,directory,source,settings,decisions,rotations):
    starts=[1]+[p for p,d in sorted(decisions.items()) if d['new_document']]
    selected=[(max(p for p in starts if p<right),right-1,right)
              for right,d in sorted(decisions.items()) if artifact_policy.candidate(d)]
    needed=sorted({p for triple in selected for p in triple})
    summary_path=directory/'summary.json'
    prior=json.loads(summary_path.read_text())
    # Direct stage resumes, as well as whole-pipeline resumes, are idempotent.
    prior=prior.get('pre_artifact_summary',prior)
    records=[];facts={};cached=0
    for page in needed:
        path=directory/'artifact_pages'/f'{page:04}.json'
        identity={'source':source,'settings':settings,'page':page,'single_image':True}
        old=json.loads(path.read_text()) if path.exists() else None
        if old is not None and old['identity']!=identity:raise ValueError('Artifact page cache identity changed')
        if old is not None and old['status']=='complete':
            facts[page]=page_artifact.validate(old['facts']);records.append(old);cached+=1;continue
        before=usage_snapshot(bundle[0]);tick=time.monotonic()
        record={'identity':identity,'attempts':old.get('attempts',0)+1 if old else 1,
                'history':[*old.get('history',[]),{k:v for k,v in old.items() if k not in ('identity','history')}] if old else []}
        try:
            image=pipeline._load_page(pdf,page,dpi)
            angle=rotations.get(page,0)
            if angle:image=image.rotate(angle,expand=True)
            client=bundle[0];has_labels=hasattr(client,'image_labels')
            old_labels=getattr(client,'image_labels',None)
            if has_labels:client.image_labels=False
            try:
                raw=pipeline._infer(page_artifact.prompt(page),[image],*bundle,logger,max_tokens=300,response_schema=page_artifact.SCHEMA)
            finally:
                if has_labels:client.image_labels=old_labels
            facts[page]=page_artifact.validate(json.loads(pipeline.clean_response(raw)))
            record.update(status='complete',facts=facts[page],raw_final=raw)
            logger.info('ARTIFACT %s p%d kind=%s',pdf.name,page,facts[page]['kind'])
        except BaseException as exc:record.update(status='failed',error=str(exc));raise
        finally:
            record.update(seconds=time.monotonic()-tick,model_usage=usage_delta(before,usage_snapshot(bundle[0])))
            atomic_json(path,record);records.append(record)
    if source_identity(pdf)!=source:raise ValueError('Source changed during artifact verification')
    final=dict(decisions);changes=[]
    for anchor,left,right in selected:
        evidence=artifact_policy.combine(facts[anchor],facts[left],facts[right])
        proposal=artifact_policy.proposal(evidence)
        if not proposal or proposal[0]==decisions[right]['new_document']:continue
        cut,rule=proposal
        final[right]={**decisions[right],'new_document':cut,'relationship':'independent' if cut else 'continuation',
                      'confidence':evidence['confidence'],'artifact_rule':rule}
        changes.append({'right_page':right,'anchor_page':anchor,'before':decisions[right]['new_document'],'after':cut,
                        'rule':rule,'facts':evidence})
    review={r['right_page']:dict(r) for r in prior.get('review_candidates',[])}
    for change in changes:
        right=change['right_page'];d=final[right]
        row=review.setdefault(right,{'right_page':right,'reasons':[],'left_heading':d['left_heading'],'right_heading':d['right_heading']})
        row.update(final_cut=d['new_document'],artifact_rule=change['rule'])
        row['reasons']=[*row['reasons'],'independent_page_artifact_verification']
    attempts=[a for r in records for a in [*r.get('history',[]),r]]
    seconds=sum(r['seconds'] for r in attempts)
    atomic_json(summary_path,{**prior,'pre_artifact_summary':prior,'artifact_pages':len(needed),
        'artifact_candidates':len(selected),'artifact_cached_pages':cached,'artifact_changes':changes,
        'artifact_processing_seconds':seconds,'seam_processing_seconds':prior['seam_processing_seconds']+seconds,
        'model_usage':summarize_usage([prior['model_usage'],*[r.get('model_usage') for r in attempts]]),
        'review_candidates':list(review.values())})
    return final
