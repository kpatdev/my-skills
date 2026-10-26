#!/usr/bin/env python3
import importlib.util
import os
import pathlib
import sys
import unittest

MODULE_PATH = pathlib.Path(__file__).parents[1] / "scripts" / "biosearch.py"
spec = importlib.util.spec_from_file_location("biosearch", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
assert spec.loader
spec.loader.exec_module(mod)

LIVE = os.environ.get("BIOSEARCH_LIVE") == "1"

ARTICLE = {
    "id": "42785112", "source": "MED", "pmid": "42785112", "pmcid": "PMC13634738",
    "doi": "10.1016/j.tjpad.2026.100677", "title": "Evoke (+) trials of <i>semaglutide</i>",
    "authorString": "Cummings JL, Scheltens P.",
    "journalInfo": {"journal": {"title": "J Prev Alz Dis"}},
    "pubTypeList": {"pubType": ["Review", "Journal Article", "Research Support, N.I.H., Extramural"]},
    "abstractText": "<h4>Background</h4> The trials &amp; outcomes.",
    "inEPMC": "Y", "citedByCount": "3", "firstPublicationDate": "2026-09-24",
}

STUDY = {
    "hasResults": True,
    "protocolSection": {
        "identificationModule": {"nctId": "NCT05891496", "briefTitle": "Semaglutide in AD"},
        "statusModule": {"overallStatus": "COMPLETED", "startDateStruct": {"date": "2023-06-20"}},
        "designModule": {"phases": ["PHASE3"], "studyType": "INTERVENTIONAL",
                         "enrollmentInfo": {"count": 23, "type": "ACTUAL"}},
        "armsInterventionsModule": {"interventions": [{"type": "DRUG", "name": "Semaglutide"}]},
    },
    "resultsSection": {"outcomeMeasuresModule": {"outcomeMeasures": [{
        "type": "PRIMARY", "title": "Change in DEGs", "timeFrame": "week 12", "unitOfMeasure": "genes",
        "groups": [{"id": "OG000", "title": "Semaglutide"}, {"id": "OG001", "title": "Placebo"}],
        "classes": [{"categories": [{"measurements": [
            {"groupId": "OG000", "value": "41.25", "spread": "29.68"},
            {"groupId": "OG001", "value": "21.00"}]}]}],
        "analyses": [{"pValue": "0.04", "statisticalMethod": "ANCOVA"}],
    }]}},
}

JATS = """<article><front><abstract><p>skip</p></abstract></front><body>
<sec><title>Introduction</title><p>Intro <italic>text</italic>.</p></sec>
<sec><title>Results</title><p>Top result.</p><sec><title>Subgroup</title><p>Nested.</p></sec></sec>
</body></article>"""


class ResolveIdTests(unittest.TestCase):
    def test_each_id_shape(self):
        cases = {
            "42785112": ("pmid", "42785112"),
            "PMID:42785112": ("pmid", "42785112"),
            "pmc13634738": ("pmc", "PMC13634738"),
            "PPR1324551": ("ppr", "PPR1324551"),
            "nct05891496": ("trial", "NCT05891496"),
            "https://doi.org/10.1101/2023.07.18.549566": ("doi", "10.1101/2023.07.18.549566"),
            "label:42bdd912-2393-44c4-b7e0-47672ca28991": ("label", "42bdd912-2393-44c4-b7e0-47672ca28991"),
            "42BDD912-2393-44C4-B7E0-47672CA28991": ("label", "42bdd912-2393-44c4-b7e0-47672ca28991"),
        }
        for raw, expected in cases.items():
            self.assertEqual(mod.resolve_id(raw), expected, raw)

    def test_unknown_id_raises(self):
        with self.assertRaises(ValueError):
            mod.resolve_id("bogus")


class LiteratureQueryTests(unittest.TestCase):
    def test_plain_query_is_scoped_to_title_abstract(self):
        q = mod.literature_query("semaglutide AND alzheimer*", source="pubmed")
        self.assertTrue(q.startswith("TITLE_ABS:(semaglutide AND alzheimer*)"))
        self.assertIn("SRC:MED", q)

    def test_fielded_query_keeps_its_own_scope(self):
        q = mod.literature_query('MESH:"Alzheimer Disease" AND semaglutide', source="pubmed")
        self.assertNotIn("TITLE_ABS", q)

    def test_scope_all_matches_full_text(self):
        self.assertNotIn("TITLE_ABS", mod.literature_query("x", source="pubmed", scope="all"))

    def test_preprint_servers(self):
        both = mod.literature_query("x", source="preprints")
        self.assertIn('PUBLISHER:"bioRxiv" OR PUBLISHER:"medRxiv"', both)
        only = mod.literature_query("x", source="preprints", server="medrxiv")
        self.assertNotIn("bioRxiv", only)

    def test_filters(self):
        q = mod.literature_query("x", source="pubmed", since=2020, pub_type="rct")
        self.assertIn("PUB_YEAR:[2020 TO 3000]", q)
        self.assertIn('PUB_TYPE:"randomized controlled trial"', q)


class ArticleRecordTests(unittest.TestCase):
    def test_normalizes_and_drops_noise_types(self):
        a = mod.article_record(ARTICLE)
        self.assertEqual(a["id"], "PMID:42785112")
        self.assertEqual(a["title"], "Evoke (+) trials of semaglutide")
        self.assertEqual(a["types"], ["Review"])
        self.assertEqual(a["abstract"], "Background The trials & outcomes.")
        self.assertTrue(a["full_text"])
        self.assertEqual(a["authors"], ["Cummings JL", "Scheltens P"])

    def test_preprint_uses_ppr_id_and_publisher(self):
        a = mod.article_record({"id": "PPR1", "source": "PPR", "doi": "10.1101/x",
                                "bookOrReportDetails": {"publisher": "bioRxiv"}})
        self.assertEqual((a["id"], a["venue"], a["source"]), ("PPR1", "bioRxiv", "preprint"))


class TrialTests(unittest.TestCase):
    def test_params(self):
        p = mod.trial_params("x", status="open,completed", phase="2,3", since=2020, with_results=True, sort="updated")
        self.assertEqual(p["filter.overallStatus"], "RECRUITING,NOT_YET_RECRUITING,ENROLLING_BY_INVITATION,COMPLETED")
        self.assertEqual(p["filter.advanced"], "(AREA[Phase]PHASE2 OR AREA[Phase]PHASE3) AND AREA[StartDate]RANGE[2020-01-01,MAX]")
        self.assertEqual(p["aggFilters"], "results:with")
        self.assertEqual(p["sort"], "LastUpdatePostDate:desc")

    def test_record_and_results(self):
        t = mod.trial_record(STUDY)
        self.assertEqual(t["id"], "NCT05891496")
        self.assertIn("n=23 |", mod.trial_meta(t))
        self.assertIn("results posted", mod.trial_meta(t))
        digest = "\n".join(mod.primary_results(STUDY))
        self.assertIn("Semaglutide: 41.25 ± 29.68 genes", digest)
        self.assertIn("p=0.04 ANCOVA", digest)


class LabelTests(unittest.TestCase):
    def test_drug_expression_ors_name_fields(self):
        expr = mod.label_search_expr(drug='Ozempic"')
        self.assertEqual(expr.count("openfda."), 3)
        self.assertNotIn('""', expr)

    def test_free_text_is_anded_and_raw_passes_through(self):
        self.assertEqual(mod.label_search_expr("lactic acidosis"), "lactic AND acidosis")
        raw = 'boxed_warning:"suicidal"'
        self.assertEqual(mod.label_search_expr(raw), raw)

    def test_record_without_openfda_and_dedupe(self):
        base = {"set_id": "a", "effective_time": "20260730", "spl_product_data_elements": ["Foo tablets"],
                "boxed_warning": ["WARNING"]}
        rec = mod.label_record(base)
        self.assertEqual((rec["name"], rec["effective"], rec["has_openfda"]), ("Foo", "2026-07-30", False))
        self.assertIn("boxed_warning", rec["sections"])
        self.assertEqual(len(mod.dedupe_labels([rec, dict(rec, id="label:b")])), 1)

    def test_section_names(self):
        self.assertEqual(mod.label_fields(["warnings"]), ["warnings_and_cautions", "warnings"])
        with self.assertRaises(ValueError):
            mod.parse_sections("nope")


class FullTextTests(unittest.TestCase):
    def test_sections_and_filter(self):
        titles, blocks = mod.fulltext_sections(JATS)
        self.assertEqual(titles, ["Introduction", "Results"])
        self.assertNotIn("skip", " ".join(text for _, text in blocks))
        results = "\n".join(mod.format_fulltext(JATS, ["results"], 0))
        self.assertIn("Nested.", results)
        self.assertNotIn("Intro text.", results)


class ClipTests(unittest.TestCase):
    def test_clip_reports_remainder(self):
        self.assertEqual(mod.clip("short", 100), "short")
        self.assertTrue(mod.clip("word " * 50, 20).endswith("chars]"))


@unittest.skipUnless(LIVE, "set BIOSEARCH_LIVE=1 to hit the live APIs")
class LiveTests(unittest.TestCase):
    def test_every_source_answers(self):
        for source in ("pubmed", "preprints"):
            total, records = mod.search_literature("semaglutide", source=source, limit=1)
            self.assertGreater(total, 0, source)
        self.assertGreater(mod.search_trials("semaglutide", limit=1)[0], 0)
        self.assertGreater(mod.search_labels(drug="semaglutide", limit=1)[0], 0)

    def test_empty_label_search_is_not_an_error(self):
        self.assertEqual(mod.search_labels("zzzqqqxx", limit=1), (0, []))


if __name__ == "__main__":
    unittest.main()
