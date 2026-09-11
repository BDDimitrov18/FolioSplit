"""V15 Tesseract orientation correction for inference images."""
from __future__ import annotations
import logging

def corroborate_tesseract(img) -> tuple[bool, int | None, float] | None:
    """
    Tesseract OSD corroborator. Abstains (returns None) on low-text pages.

    Requires: apt-get install -y tesseract-ocr && pip install pytesseract

    OSD returns a raw 'orientation' angle (clockwise CW). Mapping to CCW:
      OSD 0   → CCW 0    (upright)
      OSD 90  → CCW 270  (text runs down left edge; rotate 270° CCW to fix)
      OSD 180 → CCW 180  (upside down)
      OSD 270 → CCW 90   (text runs up right edge; rotate 90° CCW to fix)

    NOTE: Validate the mapping empirically from your test's truth-rotated rows —
    this mapping is derived from convention but should be confirmed against actual
    pages in this archive.

    Returns (is_rotated, suggested_deg_ccw, confidence), or None on abstain.
    """
    try:
        import pytesseract
    except ImportError:
        return None  # abstain if pytesseract not installed

    try:
        osd = pytesseract.image_to_osd(img, output_type=pytesseract.Output.DICT)
    except Exception:
        # "Too few characters" or any other OSD failure → abstain
        return None

    # Empirically (test_osd_mapping.py), tesseract's reported orientation angle
    # already equals the CCW degrees needed to correct the page on this corpus —
    # so the mapping is the identity. (The earlier 90<->270 swap failed the
    # synthetic round-trip test on every 90/270 case.)
    _OSD_TO_CCW = {0: 0, 90: 90, 180: 180, 270: 270}
    raw_angle = int(osd.get("orientation", 0))
    ccw_deg = _OSD_TO_CCW.get(raw_angle, 0)
    osd_conf = float(osd.get("orientation_conf", 0.0))

    # Low OSD confidence → abstain rather than mislead. Raised 2.0 → 3.0 to clear a
    # low-conf false positive (a landscape low-text page firing 180°) that kept the
    # OSD arm's degrees-exact precision below the Gate-1 90% bar. Precision-first:
    # an upright page wrongly rotated corrupts every Phase-1 query that sees it.
    if osd_conf < 3.0:
        return None

    is_rot = ccw_deg != 0
    conf_mapped = min(0.95, osd_conf / 10.0)  # rough normalisation; tune if needed
    return (is_rot, ccw_deg, conf_mapped)


def query_rotation_osd_first(img, page_num: int, logger: logging.Logger) -> int:
    """Precision-first rotation for Phase 1 integration.

    Tesseract OSD is authoritative on text pages; abstention (drawings, blank,
    low-text pages) -> 0. Rationale: an upright page wrongly rotated corrupts
    every boundary query that sees it; a rotated page left alone is merely
    today's behaviour. No model call -> zero GPU cost.
    """
    corr = corroborate_tesseract(img)
    if corr is None:
        logger.debug(f"  [ROT] p{page_num}: OSD abstained -> 0")
        return 0
    is_rot, deg, conf = corr
    if not is_rot:
        return 0
    logger.info(f"  [ROT] p{page_num}: OSD -> {deg} deg CCW (conf={conf:.2f})")
    return deg
