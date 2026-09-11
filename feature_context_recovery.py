"""Checkpointed, narrowly selected thermal and document-anchor verification.

The archive-context method enables this stage. Frozen probes precede integration;
labels are never inputs.
"""
import json
import time

import anchor_facts
import thermal_transition
import supported_receipt_policy
from model_options import usage_snapshot, usage_delta, summarize_usage
from production_state import atomic_json, source_identity


def recover(pdf, total, bundle, dpi, logger, *, pipeline, directory, source,
            settings, decisions, rotations):
    # Apply the explicit receipt convention, then freeze predicted anchors.
    initial_decisions = decisions
    decisions = supported_receipt_policy.apply(decisions)
    # New context recoveries never move the anchors within this pass.
    selected = []
    starts = [1] + [p for p, d in sorted(decisions.items()) if d['new_document']]
    for right, base in sorted(decisions.items()):
        fact_path = directory / 'facts' / f'{right:04}.json'
        if fact_path.exists():
            old = json.loads(fact_path.read_text())
            if (old['identity']['source'] != source or
                    old['identity']['settings'] != settings):
                raise ValueError('First-facts source/settings identity mismatch')
            if old['status'] != 'complete':
                raise ValueError('Context verification requires completed first facts')
            pre_fact = old['identity']['base_decision']
            if thermal_transition.needed(pre_fact, old['facts']):
                selected.append(('thermal', right - 1, right, pre_fact, old['facts']))
                continue  # One verification owns a seam; never overwrite its result.
        if anchor_facts.candidate_reason(base):
            anchor = max(p for p in starts if p < right)
            selected.append(('anchor', anchor, right, base, None))

    prior = json.loads((directory / 'summary.json').read_text())
    before_all = usage_snapshot(bundle[0])
    records, pages, final, cache_hits = [], {}, dict(decisions), 0

    def ensure(page):
        if page not in pages:
            image = pipeline._load_page(pdf, page, dpi)
            angle = rotations.get(page, 0)
            pages[page] = image.rotate(angle, expand=True) if angle else image
        return pages[page]

    def apply(kind, base, facts):
        if kind == 'thermal':
            result = thermal_transition.recover_decision(base, facts)
            result['fact_recovery'] = (result['thermal_rule']
                                      if result['new_document'] else None)
            return result
        rule = anchor_facts.recovery(facts)
        if not rule:
            return dict(base)
        return {**base, 'new_document': True, 'relationship': 'independent',
                'confidence': facts['confidence'], 'anchor_rule': rule}

    for kind, left, right, base, earlier_facts in selected:
        module = thermal_transition if kind == 'thermal' else anchor_facts
        identity = {'source': source, 'settings': settings, 'kind': kind,
                    'context_page': left, 'right_page': right,
                    'base_decision': base, 'earlier_facts': earlier_facts}
        path = directory / 'context' / kind / f'{right:04}.json'
        old = json.loads(path.read_text()) if path.exists() else None
        if old and old['identity'] != identity:
            raise ValueError('Context input changed; use a new cache namespace')
        if old and old['status'] == 'complete':
            final[right] = apply(kind, base, old['facts'])
            records.append(old)
            cache_hits += 1
            logger.info('CONTEXT CACHE %s %s p%d', pdf.name, kind, right)
            continue
        before, started = usage_snapshot(bundle[0]), time.monotonic()
        record = {'identity': identity, 'attempts': old.get('attempts', 0) + 1 if old else 1,
                  'history': [*old.get('history', []),
                              {k: v for k, v in old.items() if k not in ('identity', 'history')}] if old else []}
        try:
            raw = pipeline._infer(module.prompt(left, right), [ensure(left), ensure(right)],
                                  *bundle, logger, max_tokens=300,
                                  response_schema=module.SCHEMA)
            facts = json.loads(pipeline.clean_response(raw))
            final[right] = apply(kind, base, facts)
            record.update(status='complete', facts=facts, raw_final=raw, decision=final[right])
            logger.info('CONTEXT %s %s p%d cut=%s', pdf.name, kind, right,
                        final[right]['new_document'])
        except BaseException as exc:
            record.update(status='failed', error=type(exc).__name__ + ': ' + str(exc))
            raise
        finally:
            record.update(seconds=time.monotonic() - started,
                          model_usage=usage_delta(before, usage_snapshot(bundle[0])))
            atomic_json(path, record)
            records.append(record)
        # A sparse anchor pass must not retain every full-size rendered page.
        pages.clear()
    if source_identity(pdf) != source:
        raise ValueError('Source changed during context verification')
    attempts = [attempt for row in records for attempt in [*row.get('history', []), row]]
    usage = (summarize_usage(row.get('model_usage') for row in attempts) if attempts
             else usage_delta(before_all, usage_snapshot(bundle[0])))
    seconds = sum(row['seconds'] for row in attempts)
    review = {row['right_page']: dict(row) for row in prior.get('review_candidates', [])}
    for page, decision in final.items():
        if decision['new_document'] == initial_decisions[page]['new_document']:
            continue
        row = review.setdefault(page, {'right_page': page, 'reasons': [],
                                       'base_cut': initial_decisions[page]['new_document'],
                                       'left_heading': decision['left_heading'],
                                       'right_heading': decision['right_heading']})
        row.update(final_cut=decision['new_document'], confidence=decision['confidence'],
                   context_rule=decision.get('anchor_rule') or decision.get('thermal_rule') or decision.get('filing_unit_rule'))
        row['reasons'] = [*row['reasons'], 'typed_context_verification']
    atomic_json(directory / 'summary.json', {
        **prior, 'pre_context_summary': prior, 'context_queries': len(records),
        'cached_context': cache_hits, 'context_processing_seconds': seconds,
        'seam_processing_seconds': prior['seam_processing_seconds'] + seconds,
        'model_usage': summarize_usage([prior['model_usage'], usage]),
        'review_candidates': list(review.values())})
    return final
