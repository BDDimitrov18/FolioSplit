#!/usr/bin/env python3
"""Boundary-only production splitting with validated resume and per-source manifests.

Usage: python3 run_production.py ROOT [--files shard.txt] [--endpoint URL]
Exit 0 means every selected source is complete; failures return 1, input errors 2.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import logging
import re
from pathlib import Path
import shutil
import subprocess
import sys

from production_state import file_hash, is_complete, publish, source_identity, source_lock, state_key
from model_options import add_model_arguments, resolve_model_arguments, load_kwargs


def discover(root: Path, files: Path | None = None) -> list[Path]:
    if not root.is_dir():
        raise ValueError(f"Input directory does not exist: {root}")
    pdfs = sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf"
                  and not any(part.lower() == 'split' or re.fullmatch(r'obrab(?:\d+|oteni)?', part, re.IGNORECASE)
                              for part in p.relative_to(root).parts[:-1])
                  and not any(part.startswith(".") for part in p.relative_to(root).parts))
    if files is None:
        return pdfs
    wanted = {line.strip() for line in files.read_text(encoding="utf-8").splitlines() if line.strip()}
    available = {str(p): p for p in pdfs}
    available.update({str(p.relative_to(root)): p for p in pdfs})
    missing = wanted - available.keys()
    if missing:
        raise ValueError(f"Shard contains unknown PDF paths: {sorted(missing)}")
    return sorted({available[name] for name in wanted})


def runtime_settings(model_path: str, dpi: int, align_confirmation: bool, revision: str | None = None,
                     inference: dict | None = None) -> dict:
    versions = {}
    for package in ('pypdf', 'pdf2image', 'Pillow', 'pytesseract', 'packaging'):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    root = Path(__file__).parent
    return {"model": model_path, "model_revision": revision, "dpi": dpi, "classify": False,
            "inference": inference,
            "align_confirmation": align_confirmation, "python": sys.version.split()[0],
            "packages": versions,
            "code": {p: file_hash(root / p) for p in ("split.py", "rotation.py", "production_state.py", "run_production.py",
                                                     "model_options.py", "qwen38_client.py")}}


def preflight() -> None:
    import pytesseract  # Required: otherwise the rotation helper silently abstains.
    for program in ("tesseract", "pdftoppm", "pdfinfo"):
        if shutil.which(program) is None:
            raise RuntimeError(f"Required executable is missing: {program}")
    languages = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True, check=True)
    for language in ('osd', 'eng'):
        if language not in languages.stdout.split():
            raise RuntimeError(f'Tesseract language data is missing: {language}')


def load_model_for_settings(pipeline, settings, logger):
    from labeled_qwen38 import load_model
    return load_model(settings['model'], logger, **load_kwargs(settings))


def detect_for_settings(pipeline, pdf, total, bundle, settings, logger, checkpoint_dir, source):
    from feature_pipeline import detect
    return detect(pdf, total, *bundle, settings['dpi'], logger, pipeline=pipeline,
                  checkpoint_dir=checkpoint_dir, source=source, settings=settings)


def run(pdfs: list[Path], root: Path, pipeline, logger, settings: dict) -> int:
    model_bundle = None
    failed = []
    done = 0
    for i, pdf in enumerate(pdfs, 1):
        output = pdf.parent / "split"
        initialization_failed = False
        try:
            with source_lock(pdf, output):
                source = source_identity(pdf)
                if is_complete(pdf, output, source, settings):
                    done += 1
                    print(f"[{i}/{len(pdfs)}] SKIP (validated): {pdf.relative_to(root)}", flush=True)
                    continue
                total = len(pipeline.PdfReader(str(pdf)).pages)
                if total < 1:
                    raise ValueError(f"Empty source PDF: {pdf}")
                if model_bundle is None:
                    try:
                        preflight()
                        model_bundle = load_model_for_settings(pipeline,settings,logger)
                    except Exception:
                        initialization_failed = True
                        raise
                    logging.disable(logging.NOTSET)
                print(f"[{i}/{len(pdfs)}] {pdf.relative_to(root)}", flush=True)
                boundaries, rotations = detect_for_settings(pipeline,pdf,total,model_bundle,settings,logger,
                    output/'.state'/'feature_seams'/state_key(pdf),source)
                publish(pdf, output, source, settings, total, boundaries, rotations,
                        pipeline.split_pdf, logger, pipeline.CONFIDENCE_THRESHOLD)
                done += 1
        except Exception:
            failed.append(str(pdf.relative_to(root)))
            logger.exception("FAILED %s", pdf)
            if initialization_failed:
                break
        print(f"PROGRESS {done}/{len(pdfs)}", flush=True)
    if done != len(pdfs):
        print(f"PRODUCTION_FAILED {done}/{len(pdfs)}; failed={failed}", flush=True)
        return 1
    print(f"PRODUCTION_DONE {done}/{len(pdfs)}", flush=True)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root")
    add_model_arguments(parser)
    parser.add_argument("--files", type=Path, help="Exact relative or absolute paths for this worker")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    try:
        selected_model, revision, inference = resolve_model_arguments(args)
        pdfs = discover(root, args.files)
        if not pdfs:
            raise ValueError("No PDFs selected")
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    import split
    logger = split.setup_logging(root / "_prod_logs")
    from feature_pipeline import configure
    settings = configure(runtime_settings(selected_model, 150, False, revision, inference))
    logger.info("PRODUCTION V15: %s PDFs under %s @ 150 DPI", len(pdfs), root)
    return run(pdfs, root, split, logger, settings)


if __name__ == "__main__":
    sys.exit(main())
