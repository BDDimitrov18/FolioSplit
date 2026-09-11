# FolioSplit V15 — operating guide and project memory

This is the single documentation file for this repository. Read it before changing
the pipeline, using a GPU, evaluating results, or exporting customer documents.
The repository contains the production runtime only. Keep experiments, PDFs,
labels, logs, weights, review material and generated outputs outside Git.

## Purpose and frozen release

Split scanned Bulgarian construction/municipal archive PDFs into independently
filed documents. A new section, signature, stamp, attachment or different-looking
page is not automatically a new document. Filing context matters. The runtime
uses images and selective OCR; it does not read ground truth or retrieve examples.
It produces contiguous page groups. It cannot assemble noncontiguous documents.
Classification is disabled: output category is `00000`, with no inferred title.

**Best fully validated variant: V15.** This clean distribution was prepared on
2026-09-11 from the original repository's frozen release:

- Original repository: https://github.com/BDDimitrov18/PDFProfiling
- Original commit: `f80249c971a412d804d4dedb3705aba1d9b4ebdf`
- Original tag: `best-v15`
- Runtime at that commit: `releases/v15/runtime/`
- Original manifest SHA-256:
  `28651143e3ea6a13e971824b2062f9978230fef9509281d022491b0d1d9ba44c`
- Detailed evidence: original `releases/v15/validation-summary.json` and manifest.
- Original local working repository:
  `/Users/bozhidardimitrov/Documents/PdfCategorization`

Forty of the 45 Python modules are copied byte-for-byte. Five files were narrowed
for distribution: `split.py`, `rotation.py`, `model_options.py`,
`feature_pipeline.py`, `run_production.py`. Legacy loaders/method selection were
removed; the V15 execution stages, prompts, decisions, image handling, JSON
recovery, sampling and PDF publication were preserved. The public command pins
150 DPI, thinking OFF, greedy decoding, 4096 completion tokens and V15.
The timeout defaults to the production-tested 600 seconds. Discovery also skips
generated `obrab`, `obrabN` and `obraboteni` directories. All shipped Python
modules now participate in the checkpoint identity. A bounded job supervisor was
added. These are packaging/operation changes, not a newly GPU-benchmarked model.
New code hashes intentionally invalidate old cache namespaces.

Names such as `features_v11`, `single_page_artifacts_v12`,
`independent_identity_v13`, `filing_boundary_v5b.py` and `filing_features_v7.py`
are historical internal stage names still required by V15. They are not selectable
older releases. Do not delete or rename them based on their suffixes.

## Layout and execution order

`run_production.py` is the only production entry point. `split.py` supplies
rendering, strict model calls and PDF writing. `production_state.py` manages
locking, hashing, publication and validated resume. `feature_pipeline.py` runs:

1. Render each page at 150 DPI with Poppler. Tesseract OSD proposes orientation;
   confidence below 3 abstains. Correct inference images only. Preserve the
   original PDF pages and orientation in exports. Do not infer rotation from
   portrait/landscape dimensions: many drawings are correctly landscape.
2. Query adjacent page pairs using `filing_features.py`. Positional image labels
   prevent left/right confusion. Extract literal headings, page types, table
   structure, relationship, evidence and confidence. Apply typed feature policy.
3. Selectively refine ambiguous evidence with `feature_refinement.py`,
   `filing_features_v7.py` and `refinement_policy.py`.
4. Recover narrow document-type facts using `feature_fact_recovery.py` and
   `boundary_facts.py`/`boundary_fact_policy.py`.
5. Check structural software plots with `plot_facts.py`, then apply filing-unit
   receipt rules (`filing_unit_policy.py`).
6. Check structural facts, thermal transitions and predicted document anchors
   (`structural_*`, `feature_context_recovery.py`, `thermal_transition.py`,
   `anchor_facts.py`, `supported_receipt_policy.py`). Anchors come from predictions,
   never reference boundaries.
7. Reconcile receipt headings after the preceding model/context stages
   (`receipt_consistency.py`). Ordering prevents this rule changing prior queries.
8. Independently read selected single-page artifacts (`page_artifact.py`,
   `artifact_recovery.py`, `artifact_policy.py`). This reduces cross-image copying.
9. Apply sequential rules, then selective independent identity verification:
   `sequential_*`, `identity_selection.py`, `identity_recovery.py`,
   `independent_page_recovery.py`, `page_identity.py`, `identity_policy.py`.
   Legal and filing modules read literal personal/company/project/plot identifiers;
   crop modules corroborate narrowly defined ambiguous cases. Report OCR requires
   agreement between crops and Tesseract modes 6 and 11 (`eng`). Explicit identifier
   conflicts, including Roman plot prefixes, must remain protected.
10. Convert final starts to `DocumentBoundary` values and publish complete,
    ordered page groups. Page 1 always starts the first group. Confidence below
    0.80 marks a predicted start for review. Model confidence is not calibrated
    probability, and absence of a REVIEW suffix does not prove correctness.

`qwen38_client.py` provides strict HTTP transport and usage accounting.
`labeled_qwen38.py` adds positional image labels and greedy sampling. Independent
single-page/crop reads temporarily disable labels and restore them even on failure.
Preserve PNG encoding, image sequence, response schemas and temporary client state.

## Installation: small client, separate GPU server

Use Python 3.12 for the validated deployment. The code requires Python 3.10+ and
Unix `fcntl`; Linux is the production platform, macOS supports local client work.
There is no native Windows setup; use a Linux environment if needed.

Four direct Python dependencies are pinned in `requirements.txt`: pypdf 6.13.2,
pdf2image 1.17.0, Pillow 10.4.0 and pytesseract 0.3.13. Pytesseract also installs
`packaging` (26.3 in the checked environment). Do not install the old PyTorch,
Transformers, bitsandbytes or Qwen2.5 client stack. GPU libraries live in the
separate pinned SGLang image.

On the pod, as root, from `/workspace/pdf-splitter`:

```bash
apt-get update
apt-get install -y --no-install-recommends python3-venv poppler-utils tesseract-ocr tesseract-ocr-osd tesseract-ocr-eng util-linux
python3 -m venv /workspace/.venv-qwen38-client
/workspace/.venv-qwen38-client/bin/python -m pip install -r requirements.txt
/workspace/.venv-qwen38-client/bin/python -m pip check
tesseract --list-langs
bash scripts/start_qwen38_server.sh --check
```

Both `eng` and `osd` must appear. `pdftoppm` and `pdfinfo` must be available.
On macOS install Poppler and Tesseract through the local package manager, create
`.venv` with Python 3.12, and install the same requirements. Run
`python run_production.py --help` without loading weights. Local client operation
can use an SSH tunnel to the pod; the GPU server itself is Linux-only.

## Exact model and server identity

`data/qwen38_deployment.json` is the original compact-v3 deployment, byte-for-byte.
Its early `provenance` notes saying pending/pilot describe when it was created;
the later measured runs below supersede those notes. The historical reference to
a 16384-token experiment is not the V15 completion cap. Do not change provenance
strings casually: the entire deployment object is part of cache identity.

| Setting | Pinned value |
| --- | --- |
| Checkpoint | `RadixArk/Qwen3.8-27B-NVFP4-BF16-LMHead` |
| Revision | `009632fef96dd349150baa780c984e62e70e91fe` |
| Served model | `qwen3.8-27b-009632fe-compact-v3` |
| SGLang image | `lmsysorg/sglang@sha256:b91d664a8e4825afc16ab831c6035a6c88ac20ef8bd26da4fe2b9813a9f44376` |
| SGLang build | `5f55db35e926d50676f75b812640ea2410b0fe0e` |
| CUDA / minimum driver | `13.0.3` / `580.65.06` |
| Measured GPU | RTX 5090, 32 GB; driver `580.126.20` |
| Weights | 23,749,063,264 bytes; cache outside Git |
| Context / total KV token pool | 32768 / 32768 |
| Concurrent requests / GPUs | 1 / 1 |
| Images per request | At most 6; no video/audio |
| KV / recurrent state | FP8 E4M3 / FP32 |
| Sampling | thinking OFF, temperature 0, top-p 1, top-k 1, presence penalty 0 |
| Completion cap / HTTP timeout | 4096 tokens / 600 seconds |
| Constrained JSON | xgrammar, syntactic whitespace disabled |

The launcher supplies the remaining pinned parameters. Do not substitute the
floating image tag, auto-sized KV pool, different quantization or a newer server
while describing the run as the validated release. Endpoint model-name matching
is a check, not cryptographic proof of the remote weights/image. Inspect both.

The original auto-sized KV pool allocated 158422 tokens and a three-page smoke
ran out of GPU memory. Capping it at 32768 reserved vision memory. Compact JSON
prevents whitespace-only generation from consuming a completion budget. A length
finish or malformed final JSON gets one shared repair attempt; OFF truncation
uses bounded strings and whole-percent confidence. Further failures propagate.
Never convert a failed response into KEEP TOGETHER. Raising token limits or
turning thinking on is an experiment, not the fix for every interrupted request.

## RunPod access and persistent setup

Use a user-provided pod. Do not rent, recharge, stop or terminate one without the
corresponding user instruction. Addresses and mapped SSH ports change on restart;
obtain the current connection from RunPod. Historical IPs are not configuration.
No pod was started or contacted to prepare this clean distribution.

Keep the model cache at `/workspace/qwen38-cache`, code at
`/workspace/pdf-splitter`, input under `/workspace/input`, and job records under
`/workspace/jobs/JOB_NAME`. Confirm that `/workspace` is backed by the intended
persistent volume. A directory name alone does not guarantee persistence.
Budget space for the ~23.75 GB weights, image, original PDFs and outputs.
`/root` and `/opt` are container-local: after recreation, check packages, virtual
environment links, server interpreter and process state again. Processes never
survive a pod stop just because files persist.

The developer's existing local key is normally `~/.ssh/id_ed25519`. Reuse it; never
overwrite it. Upload only its `.pub` public key through RunPod's supported key
setup. Never place a private key, API token or downloaded documents in this repo.
Use the actual values below in a local terminal:

```bash
POD_HOST=YOUR_CURRENT_HOST
POD_PORT=YOUR_CURRENT_SSH_PORT
ssh -i ~/.ssh/id_ed25519 -p "$POD_PORT" "root@$POD_HOST"
```

If the pinned image needs SSH bootstrapping, use its web terminal to place the
public key in `/workspace/qwen38-pod-authorized_keys` and copy
`scripts/bootstrap_qwen38_runpod.sh` to `/workspace/qwen38-pod-bootstrap.sh`.
Configure the pod start command as `/bin/bash /workspace/qwen38-pod-bootstrap.sh`
and expose container TCP 22 through the provider's mapped SSH port. The script
installs/starts public-key-only SSH; it does not launch the model. Verify changed
host keys using the pod console rather than disabling host-key checking globally.

Deploy the code from this repository, separately from PDFs. Example local transfer:

```bash
git archive --format=tar HEAD -o /tmp/pdf-splitter-v15.tar
ssh -i ~/.ssh/id_ed25519 -p "$POD_PORT" "root@$POD_HOST" 'mkdir -p /workspace/pdf-splitter'
scp -i ~/.ssh/id_ed25519 -P "$POD_PORT" /tmp/pdf-splitter-v15.tar "root@$POD_HOST:/workspace/"
ssh -i ~/.ssh/id_ed25519 -p "$POD_PORT" "root@$POD_HOST" 'tar -xf /workspace/pdf-splitter-v15.tar -C /workspace/pdf-splitter'
```

Deploy into a fresh directory or check its contents before updating; extracting
an archive does not remove stale files. Record the Git commit and archive hash in
the job directory. Freeze input relative paths, byte sizes, SHA-256 hashes and page
counts before upload. Verify uploaded hashes and counts. Preserve Unicode paths.
Exclude automatic splits, thumbnails and filesystem metadata. Do not process
partially copied sources. For multiple pods, freeze disjoint source-file lists;
never split one source across workers, and do not share writable checkpoint trees.

## Starting the server

Inside the pinned pod image, after setup:

```bash
cd /workspace/pdf-splitter
mkdir -p /workspace/jobs/server
nohup bash scripts/start_qwen38_server.sh --inside-container --cache-dir /workspace/qwen38-cache > /workspace/jobs/server/server.log 2>&1 < /dev/null &
echo $! > /workspace/jobs/server/server.pid
```

Inspect existing GPU/process state before starting another server. PID files can
be stale after restart. `nvidia-smi`, the process command line and the log must
agree. The image's server Python is normally `/opt/sglang/bin/python3`; the
client uses its separate lightweight virtual environment.

SSH login shells may omit the image's PATH, CUDA and SGLang environment. If the
launcher reports a build/CUDA mismatch, read the actual pinned container's PID 1
environment and restore only PATH, CUDA_HOME, CUDA_VERSION, SGLANG_BUILD_COMMIT
and LD_LIBRARY_PATH for the launch. Do not print its entire environment (it may
contain credentials), and do not invent values just to bypass verification. An
example replacement for the server launch above, run in the pod:

```bash
nohup /opt/sglang/bin/python3 -u - > /workspace/jobs/server/server.log 2>&1 <<'PY' &
import os
from pathlib import Path
allowed = {b'PATH', b'CUDA_HOME', b'CUDA_VERSION', b'SGLANG_BUILD_COMMIT', b'LD_LIBRARY_PATH'}
env = os.environ.copy()
for item in Path('/proc/1/environ').read_bytes().split(b'\0'):
    key, sep, value = item.partition(b'=')
    if sep and key in allowed:
        env[key.decode()] = value.decode()
os.chdir('/workspace/pdf-splitter')
os.execvpe('bash', ['bash', 'scripts/start_qwen38_server.sh', '--inside-container',
                  '--cache-dir', '/workspace/qwen38-cache'], env)
PY
echo $! > /workspace/jobs/server/server.pid
```

On a separate Linux GPU host with Docker instead of an existing container, use
`bash scripts/start_qwen38_server.sh --cache-dir /your/persistent/cache`.
The launcher validates the host driver and starts the pinned image.

Wait for readiness and verify the served model:

```bash
curl --fail --silent http://127.0.0.1:8000/v1/models
```

Keep port 8000 on loopback. For a local client, open a tunnel in a separate local
terminal with `ssh -N -L 8000:127.0.0.1:8000 -i ~/.ssh/id_ed25519 -p "$POD_PORT" "root@$POD_HOST"`.
Default local inference has no external API key. The client can read
`QWEN38_API_KEY` from its environment if an authenticated server is deliberately
configured; never put credentials in the endpoint URL or deployment JSON.
Readiness is not a vision smoke test: process one selected small original and
verify the resulting manifest before launching a large batch.

## Production, supervision and resume

Run from `/workspace/pdf-splitter`. With a ready server:

```bash
/workspace/.venv-qwen38-client/bin/python run_production.py /workspace/input
```

`--files /workspace/jobs/JOB_NAME/files.txt` selects an exact subset: one relative
or absolute source path per line, no header, no comments. Unknown entries and
empty selections are errors. Discovery is recursive, excludes hidden path parts,
`split`, `obrab`, `obrabN`, and `obraboteni` beneath the selected root. Still point
the root at originals, not at an output directory. Sources with identical stems
in one directory (e.g. `scan.pdf` and `scan.PDF`) would share output names; separate
them into distinct input directories before running.

For unattended operation use the bounded Linux supervisor (requires `flock`):

```bash
mkdir -p /workspace/jobs/JOB_NAME
nohup bash scripts/run_job.sh /workspace/jobs/JOB_NAME /workspace/input --files /workspace/jobs/JOB_NAME/files.txt > /workspace/jobs/JOB_NAME/production.log 2>&1 < /dev/null &
```

Use a new job directory for each independent batch. It records `supervisor.pid`,
`worker.pid`, `attempt` and atomic `exit.code`. `PDF_CLIENT_PYTHON` may specify an
alternative absolute client interpreter path. The supervisor attempts a failing
batch at most three times, with a 15-second pause and checkpoint reuse; only exit
1 is retried. Exit 0 means every selected source validated complete, exit 1 means
failure, exit 2 means input/usage error. Interruption is recorded as 130. A hard
kill or pod loss can leave no exit code: inspect actual processes, logs and
manifests before resuming. The supervisor does not restart a dead model server.

The GPU process continues independently of the chat once detached. Do not say
"resumed" until a real worker is observed running. Do not confuse the assistant's
token budget with the model server's completion cap. If monitoring is requested,
configure it explicitly in the host application; there is no hidden scheduler in
this repository.

`split/` is created beside each source. Output names follow
`SOURCE_001_00000_.pdf`, with `_REVIEW` on low-confidence starts. Logs are in the
input root's `_prod_logs/split_log.txt`. Per-source state lives in
`split/.state/<hash-of-source-name>.json`, and seam/stage checkpoints in
`split/.state/feature_seams/<source-key>/<source-and-settings-key>/`.

Resume validates original hash/size, settings, output names/hashes, page counts and
complete contiguous coverage. Existing filenames alone are not completion.
Source locks prevent two workers publishing one source. Publication stages and
validates files, preserves replaced outputs in `split/.history/`, and writes the
completion manifest last. Consumers must respect that marker: a flat directory
cannot be replaced as one atomic operation. Source edits or changed settings/code
invalidate completion. Never manually relabel an old cache as a new variant.

Base pairs, refinements, facts, crops, OCR and final rules have separate records.
Completed source count is not current-page count: a source passes through several
stages. Inspect stage logs and checkpoint timestamps to see real progress. Keep
raw final responses, attempt histories, errors, model usage and rule changes.
Failed model calls count toward usage; unavailable usage is unknown, not zero.

## Completion and delivery

Before declaring success, verify the selected file count, exit status and every
source manifest with `production_state.is_complete` using the exact job settings.
Check source hashes, ordered page coverage, output hashes and output page counts.
For important deliveries also compare original/output page content and image
signatures, boxes and orientation; filename counts alone cannot detect corruption.

Download PDFs together with the hidden state and job logs to a staging folder,
verify transfer hashes, then deliver. An example local download (with rsync
installed on both ends) is:

```bash
rsync -a -e "ssh -i $HOME/.ssh/id_ed25519 -p $POD_PORT" "root@$POD_HOST:/workspace/input/" /path/to/local-staging/
```

Do not place a partial download over a verified delivery. Keep original PDFs
unchanged. The user's numbered `obrabN` convention is a delivery/export step,
not the driver's native output format: assign the next unused number to each
original, copy its manifest-listed split files in order, record the mapping and
verify again. Never overwrite an earlier `obrabN` or treat its existence as proof
of completion. Keep the mapping/verification report outside this repository.
Only stop a paid pod when the user has authorized it and the requested work and
download verification are complete. Terminating/deleting a volume is separate.

## Measured results and correct interpretation

These measurements belong to the original frozen V15 GPU runs, not a new GPU
benchmark of this clean packaging. All labeled cohorts below were exposed during
development. None establishes sealed-holdout accuracy.

| Cohort | V15 TP / FP / FN | V15 boundary F1 | V15 exact documents | V14 exact documents | V15 seconds/page |
| --- | --- | --- | --- | --- | --- |
| 94 sources, 3115 pages | 1223 / 54 / 68 | 95.25% | 1221 / 1377 | 1216 / 1377 | 8.34 |
| Additional 82 sources, 1793 pages | 714 / 52 / 52 | 93.21% | 708 / 845 | 705 / 845 | 7.59 |
| Earlier 44-source subset, 1223 pages | 479 / 30 / 27 | 94.38% | 477 / 545 | 473 / 545 | 8.44 |

The 44-source subset is already included in the 94: do not add it again. V14's
F1 there was 94.00%; the pre-project Qwen2.5 baseline was 88.10% and 398/545 exact
documents. V14 on the additional 82 had 713 TP, 55 FP, 53 FN, F1 92.96%; whole
sources completely correct improved from 36/82 to 37/82 with V15. The 99.84% score
was a 20-source/733-page historical subset, not all data. On the 82-source cohort,
708/845 exact documents means **83.79% exact-document recovery**, despite 93.21%
boundary F1. Never call F1 simply "accuracy" without defining it.

For boundary starts after page 1: precision = TP/(TP+FP), recall = TP/(TP+FN),
F1 = 2TP/(2TP+FP+FN). Report FP and FN separately. Report exact full reference
page-group recovery and fully correct source files alongside boundary metrics.
Honor each cohort's frozen masks and authoritative group membership; an excluded
boundary can also invalidate the preceding group's endpoint. The 82-source set
has three noncontiguous reference groups, so naive conversion to contiguous
starts produces the wrong denominator (848 rather than authoritative 845).

The September 10 production delivery processed 74 originals / 1792 pages into
784 PDFs in 13090.346 seconds (3h 38m 10s), **7.30 seconds/page**, on RTX 5090.
All 1792 exported pages passed content/orientation/coverage checks. No ground truth
was supplied, so this delivery has no measured accuracy score. Its source folder
was the user-corrected
`/Users/bozhidardimitrov/Documents/Razdelqne/Gergana-2.07.2026/New folder`.
Archive SHA-256: `a9660d976886491364ee40897fb69a43ff27b8e4d1d706d0d847657824e05ba4`.

Estimate remaining work from observed processing wall time divided by pages for
comparable completed sources, multiplied by remaining pages. Exclude setup/model
download when reporting inference throughput; include it separately in delivery
ETA. Complex legal/identity cases trigger extra queries. A single page timing is
not representative of every page. Multiple pods help when source lists are
disjoint; one server's request concurrency stays one.

## Ground truth, review and future experiments

Authoritative labels come from the original repository's PDFsam projects and
explicitly confirmed human labels. Generic `obraboteni` folders were automatic
software outputs and are NOT ground truth. The user specifically declared the
splits in the supplied `newTests` dataset to be ground truth; later datasets also
require their recorded provenance and exact source-page alignment. Directory
names alone confer no authority. Verify every reference page against its source,
coverage, duplicates, missing pages and noncontiguous groups before scoring.

The developer's visual opinion is not automatically an override of the original
labeler. The user instructed us to trust the PDFsam ground truth. Keep ambiguous
labels unchanged until explicit adjudication is supplied. Never derive test truth
from V15 predictions, automatic output folders, filename boundaries or a model's
explanation. Evaluation labels must not enter production prompt/context selection.

At release time 176 sources / 4908 pages were exposed development/regression data.
A sealed 54-source / 1817-page holdout had not been evaluated. Keep it sealed until
a candidate is frozen; after inspection it ceases to be unseen. Split data by
source/case and deduplicate related scans, not just random pages.

Historical error review PDF (outside this repository):
`/Users/bozhidardimitrov/Documents/PdfCategorization/output/pdf/pdf-splitting-all-mistakes-review-2026-09-07.pdf`.
It contains 645 unique historical review items across versions; that is not V15's
current error count. Preserve the user's annotations and original file. The user
plans to label difficult cases, with full context, confidence and reasons. Import
submitted labels as a separate versioned reference set; do not overwrite review
material or infer judgments from incomplete annotations. For any mistake inspect
the predicted anchor, adjacent/context pages, all stage outputs and final override,
not only the last two page images or an early model confidence score.

Useful lessons from the experiments:

- V15 adds narrow identity/crop/OCR corroboration to the validated approach;
  the measured gain over V14 is modest. Do not combine unrelated later ideas and
  call the result V15 or the best release without testing the full combination.
- Broad precedent retrieval (V25) regressed to 703/845 exact documents, F1 92.51%,
  about 8.59 seconds/page. Heading/type similarity can retrieve a different filing
  convention. There is no RAG database in this runtime. Semantic hard cases with
  explicit reasons might help a future experiment, but remain unvalidated.
- Removing one coordinate override (V27) improved a V14-based full 82-source run
  by one exact document; it was not validated across the old 94 and integrated
  V15. It was not promoted. CPU replay alone is not a live GPU regression.
- More thinking/context, alternative quantization and direction prompts did not
  establish a better fully validated release. A failed model loader is not an
  accuracy comparison. A promising partial subset is not a promotion result.
- Read both repairs and newly introduced errors. Shared project names, stamps,
  table headers or signatures alone are too broad to determine filing boundaries.
  Literal identifiers, explicit relationships and full document context matter.

For future development, create a `codex/` branch, preserve the best tag, describe
one hypothesis and its expected failure cases, and store all experimental scripts,
datasets and run artifacts outside this clean production repository. First test
local policy/transport/cache correctness; then compare frozen baseline and
candidate on the same complete labeled files with identical scoring contracts.
Record checkpoint/model/image/code hashes, raw responses, timing, failure counts,
repairs and harms. Use fresh isolated cache namespaces. Promote only after full
paired regression and the relevant held-out evaluation, including acceptable
runtime and no unexplained regressions. Retain the previous best for rollback.

## Distribution validation and maintenance

The clean distribution was installed into a fresh Python 3.12 virtual environment
with only the client requirements. **88 local tests passed**, plus four supervisor
scenarios covering successful retry, retry exhaustion, input failure and exclusive
locking/interruption. Supervisor checks on macOS used a small `fcntl.flock` adapter
for Linux's `flock` executable. Local checks cover standalone imports,
byte-identical policy/transport files and deployment, equivalence of the V15
detector's executable stages, pinned requests, publication/recovery and generated
folder exclusion. Relevant transport, policy, OCR/cache and publication regression
tests are run from the original repository outside this distribution. Synthetic
PDF checks exercise rendering, output and resume; mocked model answers establish
software behavior, not model accuracy. No new GPU ground-truth run was performed
for packaging. Consult the source release for the original 196-test suite and
full evaluation harness; neither is a runtime dependency.

Keep this one guide current when behavior or validated status changes. Ship only
runtime modules, the deployment JSON, requirements and operating scripts. Do not
add duplicate release trees, raw responses, saved PDFs, credentials, caches or
experiment-specific rules. The original repository and research history remain
the evidence archive. This repository has a fresh Git history. Its private GitHub
remote is https://github.com/BDDimitrov18/FolioSplit and its best-release tag is
`best-v15`.
