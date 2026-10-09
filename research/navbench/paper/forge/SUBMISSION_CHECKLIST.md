# FORGE 2027 (Data & Benchmarking) — submission checklist

Deadline: **15 Nov 2026** (AoE). Format: IEEE conference template, 4 pages + 1 page of references, double-anonymous.
Confirm the deadline and the submission system (HotCRP link) on
https://conf.researchr.org/track/forge-2027/forge-2027-data-and-benchmarking-track.

## A. Anonymous artifact (replaces `https://anonymous.4open.science/r/XXXX` in `main.tex`)

1. Build the artifact tree: `bash research/navbench/local/make_artifact.sh ~/navbench-artifact`.
   - It contains the NavBench and agentbench harnesses, all released results, G1's source (`backend/`) and
     the one-command reproduction scripts.
   - It leaves out the paper drafts, reviews and personal notes.
2. Create a **new** GitHub repository, e.g. `navbench-artifact`; a private repository is fine. Push the tree:
   `cd ~/navbench-artifact && git init && git add -A && git commit -m artifact && git remote add origin <url> && git push -u origin main`.
3. Go to https://anonymous.4open.science, sign in with GitHub, choose **Anonymize**, select the repository,
   and enter the terms to mask, one per line:
   ```
   Codexa
   codexa
   CODEXA
   rohitvijayakumar45
   rohit
   Vijayakumar
   ```
   Set an expiry date after the notification date (4 Jan 2027). Then copy the URL into the Data Availability
   section of `main.tex` and recompile.
4. Open the anonymized URL in a private window. Check that no name, username or `Codexa` string is visible,
   including in `README.md`, `FREEZE.md` and `backend/`.

## B. "85.8×" and anonymity

The prototype's public README states "85.8× fewer tokens", so a reviewer could find the authors by searching for
that figure. Options, from safest to most transparent:

| option | change | trade-off |
|---|---|---|
| 1 (recommended) | During review, remove or reword the 85.8× line in the public product README. Restore it after notification. The paper text stays unchanged. | Simple; FORGE's double-anonymous rules ask authors not to make identification easy. |
| 2 | In the paper, write "a published two-digit reduction factor (about 86×)" instead of 85.8×. | The paper still reports the replication value (85.3×); slightly vaguer. |
| 3 | Keep everything as is and rely on the reviewers not searching. | Risk of de-anonymisation. |

## C. Content checks before upload

- [ ] Large-repository section filled in, and numbers checked against `results/large/analysis/report.md`.
- [ ] Every decimal in `main.tex` traced to a released report: run the number check in
      `PRE_SUBMISSION_REVIEW.md`.
- [ ] Read the full texts of the cited arXiv papers ([4]–[8], [13], [14]), and confirm each statement made about them.
- [ ] The compiled PDF is ≤ 4 pages of content plus ≤ 1 page of references; no overfull boxes.
- [ ] No author names in the PDF metadata: `pdfinfo main.pdf` shows no Author field.
- [ ] Figures: G1 labelled "G1", never "Codexa" (`NB_ANON=1` when running `nb.figures`).
