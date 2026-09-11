"""Typed boundary pipeline with validated seam checkpoints."""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
import time

import filing_features
from model_options import usage_snapshot,usage_delta,summarize_usage
from production_state import atomic_json,file_hash,source_identity

def configure(settings, method='archive-context'):
    if method != 'archive-context':
        raise ValueError('This repository contains V15 archive-context only')
    inference = settings.get('inference', {})
    if inference.get('backend') != 'qwen38' or inference.get('thinking') != 'off':
        raise ValueError('V15 requires the pinned Qwen3.8 server with thinking off')
    if settings.get('align_confirmation'):
        raise ValueError('Aligned confirmation is not part of V15')
    result = copy.deepcopy(settings)
    result['boundary_method'] = 'features_v11'
    result['input_image_labels'] = 'positional_v1'
    result['inference']['experimental_greedy'] = True
    result['receipt_consistency'] = 'same_page_batch_ocr_v1'
    result['artifact_policy'] = 'single_page_artifacts_v12'
    result['identity_policy'] = 'independent_identity_v13'
    root = Path(__file__).resolve().parent
    # Every shipped Python module participates in checkpoint identity.
    result['code'].update({p.name: file_hash(p) for p in sorted(root.glob('*.py'))})
    return result


def cache_directory(parent,source,settings):
    key=hashlib.sha256(json.dumps({'source':source,'settings':settings},sort_keys=True).encode()).hexdigest()[:32]
    return parent/key


def detect(pdf,total,model,processor,config,dpi,logger,*,pipeline,checkpoint_dir,source,settings):
    """Labels are never accepted or read; the caller owns the source/output lock."""
    if total<1:raise ValueError('Empty source')
    if settings.get('boundary_method') != 'features_v11':
        raise ValueError('V15 settings required')
    base_module = filing_features
    base_variant = 'features_v6'
    initial_usage=usage_snapshot(model)
    checkpoint_dir=cache_directory(checkpoint_dir,source,settings)
    checkpoint_dir.mkdir(parents=True,exist_ok=True)
    pages,rotations,decisions={},{},{}
    records=[];cache_hits=0
    def ensure(page):
        if page not in pages:
            img=pipeline._load_page(pdf,page,dpi)
            if page not in rotations:
                rotations[page]=pipeline._query_rotation(img,page,model,processor,config,logger)
            angle=rotations[page]
            pages[page]=img.rotate(angle,expand=True) if angle else img
        return pages[page]
    if total==1:ensure(1)
    for right in range(2,total+1):
        path=checkpoint_dir/f'{right:04}.json'
        identity={'source':source,'settings':settings,'right_page':right}
        old=json.loads(path.read_text()) if path.exists() else None
        if old is not None and old['identity']!=identity:
            raise ValueError('Stale seam checkpoint; use a new run/output location')
        if old is not None and old['status']=='complete':
            decisions[right]=filing_features.decision(old['decision'])
            rotations.update({int(p):a for p,a in old['rotations'].items()})
            logger.info('FEATURE CACHE %s p%d',pdf.name,right)
            records.append(old);cache_hits+=1
            continue
        before=usage_snapshot(model);started=time.monotonic()
        images=[ensure(right-1),ensure(right)]
        record={'identity':identity,'rotations':{str(p):rotations[p] for p in (right-1,right)},
                'attempts':old.get('attempts',0)+1 if old else 1,
                'history':[*old.get('history',[]),{k:v for k,v in old.items() if k not in ('identity','history')}] if old else []}
        try:
            raw=pipeline._infer(base_module.prompt(base_variant,right-1,right),images,
                                model,processor,config,logger,max_tokens=300,response_schema=filing_features.SCHEMA)
            decision=filing_features.decision(json.loads(pipeline.clean_response(raw)))
            record.update(status='complete',raw_final=raw,decision=decision)
            decisions[right]=decision
            logger.debug('FEATURE RAW %s p%d: %s',pdf.name,right,raw)
            logger.info('FEATURE %s p%d new=%s recovery=%s',pdf.name,right,decision['new_document'],decision['feature_recovery'])
        except BaseException as exc:
            record.update(status='failed',error=type(exc).__name__+': '+str(exc))
            raise
        finally:
            record.update(seconds=time.monotonic()-started,model_usage=usage_delta(before,usage_snapshot(model)))
            atomic_json(path,record)
            records.append(record)
        for page in list(pages):
            if page<right:del pages[page]
    if source_identity(pdf)!=source:raise ValueError('Source changed during inference')
    attempts=[attempt for row in records for attempt in [*row.get('history',[]),row]]
    atomic_json(checkpoint_dir/'summary.json',{
        'source':source,'settings':settings,'cached_seams':cache_hits,'seams':len(records),
        'seam_processing_seconds':sum(row['seconds'] for row in attempts),
        'model_usage':summarize_usage(row.get('model_usage') for row in attempts) if attempts else usage_delta(initial_usage,usage_snapshot(model))})
    from feature_refinement import refine
    decisions=refine(pdf,total,(model,processor,config),dpi,logger,pipeline=pipeline,
                     directory=checkpoint_dir,source=source,settings=settings,
                     base_records=records,rotations=rotations)
    from feature_fact_recovery import recover
    decisions=recover(pdf,total,(model,processor,config),dpi,logger,pipeline=pipeline,
                      directory=checkpoint_dir,source=source,settings=settings,
                      decisions=decisions,rotations=rotations)
    import plot_facts
    from filing_unit_policy import apply
    decisions=recover(pdf,total,(model,processor,config),dpi,logger,pipeline=pipeline,
                      directory=checkpoint_dir,source=source,settings=settings,
                      decisions=decisions,rotations=rotations,fact_module=plot_facts,stage='plots')
    prior=decisions;decisions=apply(prior)
    summary_path=checkpoint_dir/'summary.json';summary=json.loads(summary_path.read_text())
    changes=[{'right_page':p,'before':prior[p]['new_document'],'after':d['new_document'],
              'rule':d['filing_unit_rule']} for p,d in decisions.items() if d['new_document']!=prior[p]['new_document']]
    review={r['right_page']:dict(r) for r in summary.get('review_candidates',[])}
    for change in changes:
        p=change['right_page'];d=decisions[p]
        row=review.setdefault(p,{'right_page':p,'reasons':[],'left_heading':d['left_heading'],'right_heading':d['right_heading']})
        row.update(final_cut=d['new_document'],filing_unit_rule=change['rule']);row['reasons']=[*row['reasons'],'receipt_batch_rule']
    summary.update(filing_unit_changes=changes,review_candidates=list(review.values()));atomic_json(summary_path,summary)
    import structural_fact_policy
    decisions=recover(pdf,total,(model,processor,config),dpi,logger,pipeline=pipeline,
                      directory=checkpoint_dir,source=source,settings=settings,
                      decisions=decisions,rotations=rotations,fact_module=structural_fact_policy,stage='structure')
    from feature_context_recovery import recover as recover_context
    decisions=recover_context(pdf,total,(model,processor,config),dpi,logger,pipeline=pipeline,
                              directory=checkpoint_dir,source=source,settings=settings,
                              decisions=decisions,rotations=rotations)
    # Reconcile only after every model/context stage, so this cannot change
    # prompts, query selection or predicted anchors in the recorded run.
    from receipt_consistency import apply as reconcile_receipts
    prior=decisions;decisions=reconcile_receipts(prior)
    summary_path=checkpoint_dir/'summary.json';summary=json.loads(summary_path.read_text())
    changes=[{'right_page':p,'before':prior[p]['new_document'],'after':d['new_document'],
              'rule':d['filing_unit_rule']} for p,d in decisions.items() if d['new_document']!=prior[p]['new_document']]
    review={r['right_page']:dict(r) for r in summary.get('review_candidates',[])}
    for change in changes:
        p=change['right_page'];d=decisions[p]
        row=review.setdefault(p,{'right_page':p,'reasons':[],'left_heading':d['left_heading'],'right_heading':d['right_heading']})
        row.update(final_cut=False,receipt_consistency_rule=change['rule'])
        row['reasons']=[*row['reasons'],'same_page_receipt_heading_disagreement']
    summary.update(receipt_consistency_changes=changes,review_candidates=list(review.values()))
    atomic_json(summary_path,summary)
    from artifact_recovery import recover as recover_artifacts
    decisions=recover_artifacts(pdf,total,(model,processor,config),dpi,logger,pipeline=pipeline,
                                directory=checkpoint_dir,source=source,settings=settings,
                                decisions=decisions,rotations=rotations)
    from sequential_recovery import recover as recover_sequence
    from identity_recovery import recover as recover_identity
    decisions=recover_sequence(decisions,checkpoint_dir,source,settings)
    decisions=recover_identity(pdf,total,(model,processor,config),dpi,logger,pipeline=pipeline,
                              directory=checkpoint_dir,source=source,settings=settings,
                              decisions=decisions,rotations=rotations)
    boundaries=[pipeline.DocumentBoundary(page=1,code=0,name='',confidence=1.0,flagged=False,style_signal='')]
    for page,d in sorted(decisions.items()):
        if d['new_document']:
            confidence=(d['page_type_confidence'] if d['feature_recovery'] else d['confidence'])/100
            boundaries.append(pipeline.DocumentBoundary(page=page,code=0,name='',confidence=confidence,
                              flagged=confidence<pipeline.CONFIDENCE_THRESHOLD,style_signal=d.get('identity_rule') or d.get('sequence_rule') or d.get('artifact_rule') or d.get('anchor_rule') or d.get('fact_recovery') or d['feature_recovery'] or settings.get('boundary_method','features_v6')))
    return boundaries,{p:a for p,a in rotations.items() if a}
