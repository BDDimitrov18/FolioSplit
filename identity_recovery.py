"""Terminal independent identity verification, with frozen selection and auditable changes."""
import json
import identity_selection,identity_policy,page_identity,legal_identity,filing_identity,legal_crop_policy,filing_crop_identity,report_ocr_policy,report_ocr_recovery
from independent_page_recovery import read
from model_options import summarize_usage
from production_state import atomic_json

def recover(pdf,total,bundle,dpi,logger,*,pipeline,directory,source,settings,decisions,rotations):
    selected=identity_selection.select(decisions)
    path=directory/'summary.json';prior=json.loads(path.read_text());prior=prior.get('pre_identity_summary',prior)
    records=[];model_records=[];cached=0;ocr_pages=0;final=dict(decisions);changes=[]
    def pages(requests,module,stage):
        nonlocal cached
        facts,rs,hits=read(pdf,requests,module,stage,bundle,dpi,logger,pipeline=pipeline,
                          directory=directory,source=source,settings=settings,rotations=rotations)
        records.extend(rs);model_records.extend(rs);cached+=hits;return facts
    def change(c,result,stage,evidence):
        right=c['right_page']
        if not result or result[0]==final[right]['new_document']:return
        cut,rule=result;before=final[right]['new_document']
        final[right]={**final[right],'new_document':cut,'relationship':'independent' if cut else 'continuation','identity_rule':rule}
        changes.append(dict(right_page=right,before=before,after=cut,rule=rule,stage=stage,facts=evidence))
    identity=pages([(p,'') for c in selected for p in c['context_pages']],page_identity,'identity_pages')
    filing_cases=[];legal_cases=[]
    for c in selected:
        p=c['right_page'];a,l,r=[identity[(p,'')] for p in (c['anchor_page'],p-1,p)]
        earlier=identity.get((p-2,'')) if 'review_sheet' in c['reasons'] else None
        change(c,identity_policy.proposal(a,l,r,earlier),'identity',dict(anchor=a,left=l,right=r,earlier=earlier))
        if c['legal']:legal_cases.append(c)
        if 'review_sheet' in c['reasons'] or any(f['kind'] in {'assessment_report_cover','assessment_report_body'} for f in (a,l,r)):filing_cases.append(c)
    legal=pages([(p,'') for c in legal_cases for p in (c['anchor_page'],c['right_page']-1,c['right_page'])],legal_identity,'legal_pages')
    for c in legal_cases:
        p=c['right_page'];a,l,r=[legal[(p,'')] for p in (c['anchor_page'],p-1,p)]
        change(c,legal_identity.proposal(a,l,r),'legal',dict(anchor=a,left=l,right=r))
        if legal_crop_policy.needed(a,l,r):
            crop=pages([(c['anchor_page'],'lower')],legal_identity,'legal_crops')[(c['anchor_page'],'lower')]
            change(c,legal_crop_policy.proposal(a,l,r,crop),'legal_crop',dict(anchor=a,left=l,right=r,crop=crop))
    filing=pages([(p,'') for c in filing_cases for p in c['context_pages']],filing_identity,'filing_pages')
    for c in filing_cases:
        p=c['right_page'];a,l,r=[filing[(p,'')] for p in (c['anchor_page'],p-1,p)]
        earlier=filing.get((p-2,'')) if 'review_sheet' in c['reasons'] else None
        change(c,filing_identity.proposal(a,l,r,earlier),'filing',dict(anchor=a,left=l,right=r,earlier=earlier))
        if report_ocr_policy.needed(l,r):
            crops=pages([(p-1,'wide'),(p,'wide')],filing_crop_identity,'filing_crops')
            ocr=[]
            for page in (p-1,p):
                record,hit=report_ocr_recovery.read(pdf,page,pipeline=pipeline,directory=directory,source=source,
                                                  settings=settings,rotations=rotations,dpi=dpi)
                records.append(record);cached+=int(hit);ocr_pages+=1;ocr.append([row['text'] for row in record['results']])
            left_crop,right_crop=crops[(p-1,'wide')],crops[(p,'wide')]
            change(c,report_ocr_policy.proposal(l,r,left_crop,right_crop,*ocr),'report_ocr',
                   dict(left=l,right=r,left_crop=left_crop,right_crop=right_crop,ocr_texts=ocr))
    review={r['right_page']:dict(r) for r in prior.get('review_candidates',[])}
    for item in changes:
        p=item['right_page'];d=final[p]
        row=review.setdefault(p,dict(right_page=p,reasons=[],left_heading=d['left_heading'],right_heading=d['right_heading']))
        row.update(final_cut=d['new_document'],identity_rule=item['rule'])
        row['reasons']=list(dict.fromkeys([*row['reasons'],'independent_identity_verification']))
    attempts=[a for r in records for a in [*r.get('history',[]),r]];seconds=sum(r['seconds'] for r in attempts)
    atomic_json(path,{**prior,'pre_identity_summary':prior,'identity_candidates':len(selected),'identity_changes':changes,
                     'identity_page_queries':len(records)-ocr_pages,'identity_ocr_pages':ocr_pages,'identity_cached_pages':cached,'identity_processing_seconds':seconds,
                     'seam_processing_seconds':prior['seam_processing_seconds']+seconds,
                     'model_usage':summarize_usage([prior['model_usage'],*[r.get('model_usage') for row in model_records for r in [*row.get('history',[]),row]]]),
                     'review_candidates':list(review.values())})
    return final
