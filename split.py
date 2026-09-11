"""V15 PDF rendering, validated model calls, and lossless page splitting."""
from __future__ import annotations
import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from pdf2image import convert_from_path
from pypdf import PdfReader, PdfWriter

CONFIDENCE_THRESHOLD = 0.80

def _load_page(pdf_path: Path, page_num: int, dpi: int):
    """Load a single 1-indexed PDF page as a PIL image."""
    imgs = convert_from_path(str(pdf_path), dpi=dpi, first_page=page_num, last_page=page_num)
    return imgs[0]


@dataclass
class DocumentBoundary:
    page: int
    code: int
    name: str
    confidence: float
    flagged: bool = False
    style_signal: str = ""


def setup_logging(log_dir: Path) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("pdf_splitter")
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    fh = logging.FileHandler(log_dir / "split_log.txt", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(ch)
    logger.addHandler(fh)
    return logger


def clean_response(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"```(?:json)?\s*(.*?)\s*```", r"\1", text, flags=re.DOTALL)
    return text.strip()


def _infer(prompt_text: str, images: list, model, processor, config, logger: logging.Logger,
           max_tokens: int = 200, response_schema: dict | None = None) -> str:
    """Low-level: format prompt and run generate(). Returns raw output string."""
    if isinstance(config, dict) and config.get('backend') == 'qwen38':
        from qwen38_client import Qwen38Client, Qwen38TruncatedError
        from model_options import (validate_final_json, ResponseValidationError,
                                   RESPONSE_VALIDATION_RETRIES, response_format_reminder)
        if not isinstance(model, Qwen38Client):
            raise TypeError('Qwen3.8 inference needs a verified server client')
        request_prompt = prompt_text
        bounded_response = False
        for attempt in range(RESPONSE_VALIDATION_RETRIES + 1):
            # One shared recovery budget: format repair OR one bounded-field retry
            # for an OFF completion ending with length. Other failures propagate.
            schema_kwargs = {'response_schema': response_schema} if response_schema is not None else {}
            if bounded_response:
                schema_kwargs['bounded_response'] = True
            try:
                raw = model.infer(request_prompt, images, logger, max_tokens=max_tokens, **schema_kwargs)
            except Qwen38TruncatedError:
                if model.thinking != 'off' or attempt == RESPONSE_VALIDATION_RETRIES:
                    raise
                bounded_response = response_schema is not None
                logger.warning('Qwen3.8 OFF completion truncated; retrying once (bounded fields=%s)', bounded_response)
                continue
            try:
                return validate_final_json(raw, response_schema)
            except ResponseValidationError as error:
                logger.warning('Qwen3.8 invalid final format (attempt %d/%d): %s; final=%r',
                               attempt + 1, RESPONSE_VALIDATION_RETRIES + 1, error, raw)
                if attempt == RESPONSE_VALIDATION_RETRIES:
                    raise
                request_prompt = prompt_text + response_format_reminder(response_schema)
    raise ValueError('Only the pinned Qwen3.8 V15 client is supported')



def _query_rotation(img, page_num: int, model, processor, config, logger: logging.Logger) -> int:
    """OSD-first rotation (no model call)."""
    from rotation import query_rotation_osd_first
    return query_rotation_osd_first(img, page_num, logger)


def safe_filename(name: str, max_len: int = 50) -> str:
    safe = re.sub(r'[/\\:*?"<>|]', "-", name).strip()
    safe = re.sub(r"\s+", "_", safe)
    return safe[:max_len]


def split_pdf(
    pdf_path: Path,
    boundaries: list,
    output_dir: Path,
    logger: logging.Logger,
) -> list:
    reader = PdfReader(str(pdf_path))
    total = len(reader.pages)
    output_dir.mkdir(parents=True, exist_ok=True)

    stem = pdf_path.stem
    outputs = []

    for i, boundary in enumerate(boundaries):
        end_page = boundaries[i + 1].page - 1 if i + 1 < len(boundaries) else total

        writer = PdfWriter()
        for p in range(boundary.page - 1, end_page):
            writer.add_page(reader.pages[p])

        name_safe = safe_filename(boundary.name)
        flag = "_REVIEW" if boundary.flagged else ""
        out_path = output_dir / f"{stem}_{i + 1:03d}_{boundary.code:05d}_{name_safe}{flag}.pdf"

        with open(out_path, "wb") as f:
            writer.write(f)

        page_range = (
            f"page {boundary.page}"
            if boundary.page == end_page
            else f"pages {boundary.page}–{end_page}"
        )
        conf_str = f"{boundary.confidence:.0%}"
        style_str = f", style: \"{boundary.style_signal}\"" if boundary.style_signal else ""
        logger.info(f"  → {out_path.name}  ({page_range}, conf={conf_str}{style_str})")
        outputs.append(out_path)

    return outputs
