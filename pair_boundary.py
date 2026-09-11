"""Experimental direct seam classification; no labels or cached decisions in prompts."""
from __future__ import annotations

SCHEMA = {'left_heading': str, 'right_heading': str, 'relationship': str,
          'evidence': str, 'new_document': bool, 'confidence': 'confidence'}

COMMON = '''You are separating scanned Bulgarian construction-archive documents.
The first image is page {left}; the second image is page {right}.
Decide ONLY whether a new document starts at page {right}.
Read visible evidence before deciding. A new page, heading, signature, stamp,
layout change or table is not by itself a new document. Determine the relationship
between the pages. Keep continuation text, tables and closing signature pages
together. A separately issued letter, permit, certificate, insurance policy,
contract or deed can be a new document even when it concerns the same building
and has the same issuer or layout. Do not invent unreadable identifiers or names.
Use relationship "independent", "continuation", "attachment", "section",
"form_series", or "uncertain". Confidence describes visible evidence, 0 to 100.
'''

ARCHIVE = '''
Filing conventions for this archive:
- A sequence of municipal review/opinion sheets with fields Обект, Част,
  становище/забележки and дата за връщане belongs together for the same project.
  Different reviewing disciplines, signatures, dates or notes within that sequence
  are entries, not separately issued documents. Do not infer a different project
  from uncertain handwriting.
- Postal delivery/return receipts documenting the preceding letter or permit are
  its attachments. Consecutive delivery-receipt slips remain grouped; a new
  recipient or tracking number alone does not start a new archive document.
- A project cover, contents, explanatory note, calculations and drawing sheets
  can form one project volume. A heading such as СЪДЪРЖАНИЕ, ОБЯСНИТЕЛНА ЗАПИСКА,
  КОЛИЧЕСТВЕНА СМЕТКА or ГРАФИЧНА ЧАСТ alone does not prove a new volume. Look for
  an independently introduced volume/discipline, not just a section within it.
- Contract terms (Търговски условия), clauses and signature/approval pages stay
  with their contract. A fresh title on an attachment is insufficient to split it.
- Preserve genuinely separate official instruments and standalone documents;
  sharing a project, stamp or organization does not make them continuations.
'''

OUTPUT = '''
Return one JSON object with these fields in this order:
{"left_heading":"literal top heading or empty", "right_heading":"literal top heading or empty",
"relationship":"one category", "evidence":"one brief sentence identifying visible evidence",
"new_document":true/false, "confidence":0-100}.
Use new_document=true only for an independent document, not a continuation,
attachment, section or form-series entry. If genuinely uncertain, say so.
'''


def prompt(variant, left, right):
    if variant not in ('relation_v1', 'archive_v2'):
        raise ValueError('Unknown pair-boundary variant')
    if type(left) is not int or type(right) is not int or left < 1 or right != left + 1:
        raise ValueError('A seam must contain consecutive source pages')
    return COMMON.format(left=left, right=right) + (ARCHIVE if variant == 'archive_v2' else '') + OUTPUT


def decision(data):
    from model_options import validate_query_fields
    validate_query_fields(data, SCHEMA)
    if data['relationship'] not in ('independent', 'continuation', 'attachment', 'section', 'form_series', 'uncertain'):
        raise ValueError('Unknown relationship category')
    if data['new_document'] and data['relationship'] != 'independent':
        raise ValueError('Positive boundary contradicts relationship category')
    return data
