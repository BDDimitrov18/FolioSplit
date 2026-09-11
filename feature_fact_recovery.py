"""Optional typed-facts recovery after the conservative filing refinement."""
import json
import time
import boundary_fact_policy
from production_state import atomic_json,source_identity
from model_options import usage_snapshot,usage_delta,summarize_usage


def recover(pdf,total,bundle,dpi,logger,*,pipeline,directory,source,settings,decisions,rotations,fact_module=boundary_fact_policy,stage="facts"):
    prefix={'facts':'fact','plots':'plot','structure':'structural'}[stage]
    prior_summary=json.loads((directory/'summary.json').read_text())
    before_all=usage_snapshot(bundle[0]);pages={};records=[];cache_hits=0;final=dict(decisions)
    def ensure(page):
        if page not in pages:
            img=pipeline._load_page(pdf,page,dpi);angle=rotations.get(page,0)
            pages[page]=img.rotate(angle,expand=True) if angle else img
        return pages[page]
    for right,base in sorted(decisions.items()):
        reason=fact_module.candidate_reason(base)
        if not reason:continue
        path=directory/stage/f'{right:04}.json'
        identity={'source':source,'settings':settings,'right_page':right,'base_decision':base}
        old=json.loads(path.read_text()) if path.exists() else None
        if old and old['identity']!=identity:raise ValueError('Fact-recovery input changed; use a new cache namespace')
        if old and old['status']=='complete':
            final[right]=fact_module.recover_decision(base,old['facts'])
            records.append(old);cache_hits+=1;logger.info('FACTS CACHE %s p%d',pdf.name,right);continue
        before=usage_snapshot(bundle[0]);started=time.monotonic()
        record={'identity':identity,'candidate_reason':reason,'attempts':old.get('attempts',0)+1 if old else 1,
                'history':[*old.get('history',[]),{k:v for k,v in old.items() if k not in ('identity','history')}] if old else []}
        try:
            raw=pipeline._infer(fact_module.prompt(right-1,right),[ensure(right-1),ensure(right)],
                                *bundle,logger,max_tokens=300,response_schema=fact_module.SCHEMA)
            facts=json.loads(pipeline.clean_response(raw))
            final[right]=fact_module.recover_decision(base,facts)
            record.update(status='complete',facts=facts,raw_final=raw,decision=final[right])
            logger.info('FACTS %s p%d recovery=%s',pdf.name,right,final[right].get('fact_recovery') or final[right].get('plot_rule') or final[right].get('structural_rule'))
        except BaseException as exc:
            record.update(status='failed',error=type(exc).__name__+': '+str(exc));raise
        finally:
            record.update(seconds=time.monotonic()-started,model_usage=usage_delta(before,usage_snapshot(bundle[0])))
            atomic_json(path,record);records.append(record)
        for page in list(pages):
            if page<right:del pages[page]
    if source_identity(pdf)!=source:raise ValueError('Source changed during fact recovery')
    attempts=[attempt for row in records for attempt in [*row.get('history',[]),row]]
    usage=summarize_usage(row.get('model_usage') for row in attempts) if attempts else usage_delta(before_all,usage_snapshot(bundle[0]))
    seconds=sum(row['seconds'] for row in attempts)
    review={row['right_page']:dict(row) for row in prior_summary.get('review_candidates',[])}
    for page,d in final.items():
        if d['new_document']!=decisions[page]['new_document']:
            row=review.setdefault(page,{'right_page':page,'reasons':[],'base_cut':decisions[page]['new_document'],
                                      'left_heading':d['left_heading'],'right_heading':d['right_heading']})
            row.update(final_cut=d['new_document'],confidence=d['confidence'],typed_rule=d.get('fact_recovery') or d.get('plot_rule') or d.get('structural_rule'))
            row['reasons']=[*row['reasons'],{'facts':'typed_fact_recovery','plots':'typed_plot_verification','structure':'typed_structural_verification'}[stage]]
    atomic_json(directory/'summary.json',{
        **prior_summary,f'pre_{stage}_summary':prior_summary,f'{prefix}_queries':len(records),f'cached_{stage}':cache_hits,
        f'{prefix}_processing_seconds':seconds,'seam_processing_seconds':prior_summary['seam_processing_seconds']+seconds,
        'model_usage':summarize_usage([prior_summary['model_usage'],usage]),'review_candidates':list(review.values())})
    return final
