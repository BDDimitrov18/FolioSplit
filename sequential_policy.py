"""Frozen terminal filing rules using existing page evidence, never labels."""
import re

def apply(decisions,anchor_facts):
    final={p:dict(d) for p,d in decisions.items()}
    for page,d in decisions.items():
        following=decisions.get(page+1)
        rule=None;cut=d['new_document']
        if (cut and d.get('fact_recovery')=='cover_to_contents'
                and d.get('confidence',0)>=90
                and re.search(r'съдържание',d.get('right_heading',''),re.I)
                and following and following['new_document']
                and min(following.get('confidence',0),following.get('page_type_confidence',0))>=90
                and re.search(r'удостоверение',following.get('right_heading',''),re.I)
                and re.search(r'qualification|правоспособност|проектантск|квалификац',
                              following.get('right_heading','')+' '+following.get('evidence',''),re.I)):
            cut=False;rule='cover_and_short_contents_before_credential'
        facts=anchor_facts.get(page,{})
        if (not d['new_document'] and facts.get('confidence',0)>=90
                and facts.get('right_fresh_start') is True
                and facts.get('anchor_kind')=='technical_assignment'
                and facts.get('right_kind')=='quantity_schedule'
                and re.search(r'количествен\w*\s+сметка\s+на\s+материал',facts.get('right_heading',''),re.I)):
            cut=True;rule='assignment_to_named_materials_schedule'
        if rule:
            final[page].update(new_document=cut,relationship='independent' if cut else 'continuation',sequence_rule=rule)
    return final
