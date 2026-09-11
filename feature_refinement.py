"""Selective second pass over cached features_v6 evidence, without reference labels."""
import json
import time
import filing_features_v7
from refinement_policy import choose
from production_state import atomic_json,file_hash,source_identity
from model_options import usage_snapshot,usage_delta,summarize_usage


def refine(pdf,total,bundle,dpi,logger,*,pipeline,directory,source,settings,base_records,rotations):
    initial_usage=usage_snapshot(bundle[0])
    records={int(row['identity']['right_page']):row for row in base_records}
    base_summary=json.loads((directory/'summary.json').read_text())
    pages={};attempt_records=[];decisions={};cache_hits=0
    def ensure(page):
        if page not in pages:
            img=pipeline._load_page(pdf,page,dpi);angle=rotations.get(page,0)
            pages[page]=img.rotate(angle,expand=True) if angle else img
        return pages[page]
    for right,base in sorted(records.items()):
        reason=filing_features_v7.candidate_reason(base['decision'])
        if not reason:
            decisions[right]=base['decision'];continue
        next_heading=records[right+1]['decision']['right_heading'] if right<total else ''
        path=directory/'refinements'/f'{right:04}.json'
        identity={'source':source,'settings':settings,'right_page':right,
                  'base_sha256':file_hash(directory/f'{right:04}.json'),'next_heading':next_heading}
        old=json.loads(path.read_text()) if path.exists() else None
        if old and old['identity']!=identity:raise ValueError('Refinement input changed; use a new cache namespace')
        if old and old['status']=='complete':
            final=choose(base['decision'],old['decision']);decisions[right]=final
            attempt_records.append(old);cache_hits+=1
            logger.info('REFINEMENT CACHE %s p%d',pdf.name,right);continue
        before=usage_snapshot(bundle[0]);started=time.monotonic()
        record={'identity':identity,'candidate_reason':reason,'attempts':old.get('attempts',0)+1 if old else 1,
                'history':[*old.get('history',[]),{k:v for k,v in old.items() if k not in ('identity','history')}] if old else []}
        try:
            images=[ensure(right-1),ensure(right)]
            raw=pipeline._infer(filing_features_v7.prompt('features_v7',right-1,right,next_heading),images,
                                *bundle,logger,max_tokens=300,response_schema=filing_features_v7.SCHEMA)
            proposed=filing_features_v7.decision(json.loads(pipeline.clean_response(raw)))
            final=choose(base['decision'],proposed);decisions[right]=final
            record.update(status='complete',raw_final=raw,decision=proposed,final_decision=final)
            logger.info('REFINEMENT %s p%d base=%s final=%s policy=%s',pdf.name,right,
                        base['decision']['new_document'],final['new_document'],final['refinement_policy'])
        except BaseException as exc:
            record.update(status='failed',error=type(exc).__name__+': '+str(exc));raise
        finally:
            record.update(seconds=time.monotonic()-started,model_usage=usage_delta(before,usage_snapshot(bundle[0])))
            atomic_json(path,record);attempt_records.append(record)
        for page in list(pages):
            if page<right:del pages[page]
    if source_identity(pdf)!=source:raise ValueError('Source changed during refinement')
    attempts=[attempt for row in attempt_records for attempt in [*row.get('history',[]),row]]
    extra_usage=summarize_usage(row.get('model_usage') for row in attempts) if attempts else usage_delta(initial_usage,usage_snapshot(bundle[0]))
    extra_seconds=sum(row['seconds'] for row in attempts)
    proposals={int(row['identity']['right_page']):row['decision'] for row in attempt_records}
    review=[]
    for right,final in sorted(decisions.items()):
        base=records[right]['decision'];proposed=proposals.get(right,base)
        reasons=[]
        if proposed.get('model_new_document',proposed['new_document']) != (proposed.get('model_relationship',proposed['relationship'])=='independent'):reasons.append('inconsistent_model_fields')
        if base['new_document']!=proposed['new_document']:reasons.append('passes_disagree')
        if proposed['new_document']!=final['new_document']:reasons.append('scope_guard_preserved_cut')
        if final['relationship']=='uncertain' or final['confidence']<90:reasons.append('uncertain_evidence')
        if final.get('feature_recovery'):reasons.append('typed_feature_recovery')
        if reasons:
            review.append({'right_page':right,'reasons':reasons,'base_cut':base['new_document'],
                           'proposed_cut':proposed['new_document'],'final_cut':final['new_document'],
                           'left_heading':final['left_heading'],'right_heading':final['right_heading'],
                           'evidence':final['evidence'],'confidence':final['confidence']})
    atomic_json(directory/'summary.json',{
        **base_summary,'base_summary':base_summary,'review_candidates':review,'refinement_queries':len(attempt_records),
        'cached_refinements':cache_hits,'refinement_processing_seconds':extra_seconds,
        'seam_processing_seconds':base_summary['seam_processing_seconds']+extra_seconds,
        'model_usage':summarize_usage([base_summary['model_usage'],extra_usage])})
    return decisions
