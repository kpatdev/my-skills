---
name: biosearch
description: Search biomedical evidence through the biosearch CLI, covering PubMed, bioRxiv/medRxiv preprints, ClinicalTrials.gov, and FDA drug labels. Use when asked to find studies, papers, preprints, or clinical trials on a topic; to research a drug, disease, or treatment question; or to look up FDA label content such as indications, boxed warnings, dosing, or interactions.
---

# Biosearch

Treat every answer as an **evidence trail**: each claim traces to a record ID that biosearch returned in this session, and each record is placed on the evidence hierarchy before it carries weight.

## Establish the command surface

Run:

```sh
scripts/biosearch --help
scripts/biosearch <command> --help
```

Resolve `scripts/biosearch` relative to this file; under Claude Code, `${CLAUDE_SKILL_DIR}/scripts/biosearch` reaches it from any install location. The wrapper runs through `uv`, so `uv` must be on PATH. Every source is free and keyless; an `OPENFDA_API_KEY` in the environment only raises openFDA's rate limit.

Run `--help` for each command the request needs. This step is complete when `--help` has printed for every command you will use.

## Frame the question

Pull out the parts of the request that become search terms: the intervention or exposure, the condition, and the outcome when one is named. For each part, gather the variants a database might index under:

- generic and brand drug names (`semaglutide`, `Ozempic`, `Wegovy`), plus the drug class when class evidence counts (`"GLP-1 receptor agonist"`);
- wildcard stems, since matching is literal: `semaglutide AND alzheimer*` finds 4 preprints where `semaglutide AND alzheimer` finds none;
- synonyms joined with `OR` in parentheses: `(alzheimer* OR dementia)`.

Query syntax for each source lives in [`references/QUERIES.md`](references/QUERIES.md). Read it before writing a fielded query (MeSH, author, title-only), a trial phase or status filter, or an openFDA field search. This step is complete when every part of the question has its variants written down as a query string.

## Sweep

Fan the query out to every source at once:

```sh
scripts/biosearch search 'semaglutide AND (alzheimer* OR dementia)' --drug semaglutide
```

Add `--drug` whenever a drug is in scope. FDA labels are searched only when it is given. Each block header reports total matches, and that count is your signal for the next query:

- **0 or a handful**: broaden with more synonyms, a wildcard, the drug class, or `--scope all` to match full text.
- **Thousands**: narrow with a second concept, `--since`, or the per-source filters below.

This step is complete when every source has returned on-topic records, or has returned zero after one broadened retry.

## Drill

Go deeper with per-source commands, matched to what the request needs:

```sh
scripts/biosearch pubmed '<query>' --type meta-analysis --sort cited    # strongest synthesized evidence first
scripts/biosearch pubmed '<query>' --type rct --abstracts               # primary randomized evidence
scripts/biosearch trials --intervention semaglutide --condition "alzheimer disease" --phase 2,3 --summaries
scripts/biosearch trials --intervention semaglutide --status open       # what is enrolling now
scripts/biosearch labels --drug semaglutide
scripts/biosearch get <id>                                              # abstract, MeSH, trial design, label sections
scripts/biosearch get <PMID or PMCID> --full --sections results,discussion
```

Europe PMC relevance ranking favors recent papers, so landmark papers surface with `--sort cited`. `get` takes any ID a search printed: `PMID:…`, `PMC…`, `PPR…`, a DOI, an `NCT…` ID, or `label:…`.

Trials that show `no results posted` often have results published in journals. Search the NCT ID itself with `pubmed '<NCT id>' --scope all` before you report a trial as unreported.

This step is complete when every record you will cite has been read through `get`, or through an abstract shown by `--abstracts`/`--summaries`. Only those records go into the answer.

## Deliver

Match the shape of the answer to the request.

**"Find studies on X"** gets a list grouped by source. Each entry gives the ID, title, venue and year, type, and a line on why it fits. End with the queries you ran and the total match counts, so the user can see how big each field is.

**"Research X"** gets a synthesis organized by the evidence hierarchy, strongest first:

1. FDA label content: what is approved, plus boxed warnings and contraindications, for US labels.
2. Meta-analyses and systematic reviews.
3. Randomized trials, both published and results posted on ClinicalTrials.gov.
4. Observational and real-world studies.
5. Ongoing trials, with status and expected completion.
6. Preprints, labeled as not peer reviewed every time they are cited.
7. Mechanistic and animal work, labeled as such.

Cite the ID inline for every claim (`PMID:42785112`, `NCT04777409`, `label:42bdd912-…`). Where sources conflict, say so, and state which side the stronger evidence supports. Close with the gaps (questions the sweep could not answer), the queries run, and today's date as the search date.

The answer is complete when every claim carries an ID retrieved this session, every preprint is labeled, and the queries are listed.
