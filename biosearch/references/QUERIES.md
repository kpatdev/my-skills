# Query syntax by source

What each upstream API accepts behind biosearch's flags, and the quirks no `--help` mentions.

## Literature: `pubmed`, `preprints`, `search`

These go to Europe PMC. Its index covers PubMed and the bioRxiv and medRxiv servers.

- Plain words are ANDed. Use `OR` and `NOT` in capitals and parentheses for grouping, and double quotes for phrases: `"heart failure"`. Unquoted `heart failure` matches *heart* and *failure* anywhere.
- `*` is a trailing wildcard: `cardiomyopath*`.
- By default the whole query is wrapped in `TITLE_ABS:(…)`. A query containing any field prefix (`TITLE:`, `MESH:`, …) skips the wrapping, so the fields you name are the scope. `--scope all` also matches full text: higher recall, more passing mentions.
- Useful fields:

| Field | Example |
|---|---|
| `TITLE:` | `TITLE:"semaglutide"` |
| `ABSTRACT:` | `ABSTRACT:(hba1c AND "weight loss")` |
| `MESH:` | `MESH:"Alzheimer Disease"` (PubMed records only; preprints carry no MeSH) |
| `AUTH:` | `AUTH:"Cummings JL"` |
| `JOURNAL:` | `JOURNAL:"lancet"` |
| `GRANT_AGENCY:` | `GRANT_AGENCY:"NIA"` |
| `OPEN_ACCESS:` | `OPEN_ACCESS:y` (full text retrievable with `get --full`) |

- `--type` maps to PubMed publication types. Preprints carry none, so `preprints` has no `--type`.
- Titles in `[square brackets]` are English translations of non-English papers.
- `get --full` works only when the search line says `full text available`. Section titles differ from paper to paper, so `get --full` prints the list first. Pass substrings of those titles to `--sections`.
- `get` resolves preprints from other servers, such as Research Square. The `preprints` search covers only bioRxiv and medRxiv.

## Trials: `trials`

These go to the ClinicalTrials.gov API v2.

- The positional query searches every field. `--condition` and `--intervention` search only those fields and are more precise. Combine them freely.
- The query language is Essie: `AND`/`OR`/`NOT`, quoted phrases, and synonym expansion (e.g. `heart attack` also finds *myocardial infarction*).
- `--status open` means recruiting, not yet recruiting, or enrolling by invitation.
- `--since` filters on the trial's start date.
- `n=… (est.)` is target enrollment. Without `(est.)` it is actual enrollment.
- `get NCT…` digests posted primary results when the trial has them. `get NCT… --json` returns the raw record, including the full `resultsSection`.

## Drug labels: `labels`

These go to openFDA `drug/label`, which holds US Structured Product Labels.

- `--drug NAME` matches brand, generic, or substance name. Prefer it whenever the drug is known.
- A free-text query searches every label section, and its words are ANDed. A query with `:` or quotes is passed through as raw openFDA syntax, where a space means OR and `AND` must be written explicitly: `boxed_warning:"suicidal" AND openfda.route:"oral"`.
- One product carries many labels, from repackagers and relabelers. biosearch keeps the newest label per product name and route.
- A label marked `no openFDA metadata` is usually an unapproved drug or an OTC monograph product. Brand and manufacturer come from the label text.
- `get label:… --sections` takes the short names that `labels --help` and `get --help` list, or `all`. Each section is clipped to `--max-chars`.
- Labels show approved US use. Off-label evidence lives in the literature.
