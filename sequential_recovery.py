"""Apply terminal sequence evidence without extra model calls."""
import json
from production_state import atomic_json
from sequential_policy import apply

def recover(decisions, directory, source, settings):
    anchors={}
    for page in decisions:
        path=directory/'context'/'anchor'/f'{page:04}.json'
        if not path.exists():continue
        record=json.loads(path.read_text())
        if record['identity']['source']!=source or record['identity']['settings']!=settings:
            raise ValueError('Sequence anchor source/settings mismatch')
        if record['status']!='complete':raise ValueError('Sequence requires complete anchor facts')
        anchors[page]=record['facts']
    final=apply(decisions,anchors)
    path=directory/'summary.json';prior=json.loads(path.read_text())
    prior=prior.get('pre_sequence_summary',prior)
    changes=[dict(right_page=p,before=decisions[p]['new_document'],after=d['new_document'],rule=d['sequence_rule'])
             for p,d in sorted(final.items()) if d['new_document']!=decisions[p]['new_document']]
    review={r['right_page']:dict(r) for r in prior.get('review_candidates',[])}
    for change in changes:
        p=change['right_page'];d=final[p]
        row=review.setdefault(p,dict(right_page=p,reasons=[],left_heading=d.get('left_heading',''),right_heading=d.get('right_heading','')))
        row.update(final_cut=d['new_document'],sequence_rule=change['rule'])
        row['reasons']=[*row['reasons'],'sequence_evidence_rule']
    atomic_json(path,{**prior,'pre_sequence_summary':prior,'sequence_changes':changes,'review_candidates':list(review.values())})
    return final
