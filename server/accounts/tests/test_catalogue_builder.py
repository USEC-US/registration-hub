import json
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from accounts.services.catalogue import build_catalogue


class CatalogueBuilderTests(SimpleTestCase):
    def test_retirement_survives_source_refresh(self):
        moet = [{"Id": "school-id", "MA": "EX", "TEN_DON_VI": "Example University"}]
        for base in (
            [],
            [{"value": "123", "label": "Example University", "code": "EX"}],
        ):
            initial, _ = build_catalogue(base, moet, [], {}, "rev")
            value = initial[0]["value"]
            result, _ = build_catalogue(
                initial, moet, [], {"retired": {value: "Retired"}}, "rev"
            )
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["value"], value)
            self.assertEqual(result[0]["review_status"], "REJECTED")

    def test_corrected_domain_mapping_removes_previous_ownership(self):
        base = [
            {
                "value": "wrong",
                "label": "Wrong University",
                "domains": ["school.edu.vn"],
                "provenance": [
                    {"source": "swot", "domain": "school.edu.vn", "revision": "old"}
                ],
            },
            {"value": "right", "label": "Right University"},
        ]
        records, _ = build_catalogue(
            base,
            [],
            [{"domain": "school.edu.vn", "names": ["Right University"]}],
            {"swot": {"school.edu.vn": "right"}},
            "new",
        )
        by_id = {r["value"]: r for r in records}
        self.assertEqual(by_id["wrong"]["domains"], [])
        self.assertFalse(
            any(
                p.get("domain") == "school.edu.vn" for p in by_id["wrong"]["provenance"]
            )
        )
        self.assertEqual(by_id["right"]["domains"], ["school.edu.vn"])

    def test_swot_aliases_do_not_trigger_transitive_identity_matches_on_refresh(self):
        base = [{"value": "1", "label": "Alpha University"}]
        swot = [
            {"domain": "a.edu.vn", "names": ["Beta University"]},
            {"domain": "z.edu.vn", "names": ["Alpha University", "Beta University"]},
        ]
        first, _ = build_catalogue(base, [], swot, {}, "rev")
        second, _ = build_catalogue(first, [], swot, {}, "rev")
        self.assertEqual(first, second)
        self.assertEqual(second[0]["domains"], ["z.edu.vn"])

    def test_pinned_catalogue_keeps_ids_and_rebuilds_without_duplicate_domains(self):
        root = Path(settings.BASE_DIR) / "data" / "institutions"

        def read(name):
            return json.loads((root / name).read_text())

        legacy = read("legacy.json")["data"]
        moet, swot, overrides = (
            read("moet.json"),
            read("swot.json"),
            read("overrides.json"),
        )
        records, _ = build_catalogue(
            legacy, moet["data"], swot["data"], overrides, swot["revision"]
        )
        self.assertTrue(
            {r["value"] for r in legacy}.issubset({r["value"] for r in records})
        )
        rebuilt, _ = build_catalogue(
            records, moet["data"], swot["data"], overrides, swot["revision"]
        )
        self.assertEqual(records, rebuilt)
        by_value = {r["value"]: r for r in records}
        self.assertIn("HÀ NỘI", by_value["215"]["label"])
        self.assertIn("HỒ CHÍ MINH", by_value["222"]["label"])
        self.assertIn("hcmus.edu.vn", by_value["222"]["domains"])
        self.assertIn("hcmut.edu.vn", by_value["218"]["domains"])
        self.assertNotIn("hcmut.edu.vn", by_value["57"]["domains"])
        self.assertIn("ptithcm.edu.vn", by_value["8"]["domains"])
        self.assertNotIn("ptithcm.edu.vn", by_value["7"]["domains"])
        self.assertEqual(by_value["529"]["review_status"], "REJECTED")
        self.assertEqual(by_value["222"]["location"], "")
        self.assertIn("TP. Hồ Chí Minh", by_value["222"]["aliases"])

    def test_moet_retains_existing_identity_and_swot_adds_domains(self):
        base = [
            {
                "value": "222",
                "label": "Science HCM",
                "code": "QST",
                "shortName": "HCMUS",
            }
        ]
        moet = [{"Id": "upstream-hcm", "MA": "QST", "TEN_DON_VI": "Science, VNU-HCM"}]
        swot = [{"domain": "hcmus.edu.vn", "names": ["University of Science, VNU-HCM"]}]
        records, report = build_catalogue(
            base,
            moet,
            swot,
            {"moet": {"QST": "222"}, "swot": {"hcmus.edu.vn": "222"}},
            "revision",
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["value"], "222")
        self.assertEqual(records[0]["label"], "Science, VNU-HCM")
        self.assertEqual(records[0]["domains"], ["hcmus.edu.vn"])
        self.assertIn("Science HCM", records[0]["aliases"])
        rebuilt, _ = build_catalogue(
            records,
            moet,
            swot,
            {"moet": {"QST": "222"}, "swot": {"hcmus.edu.vn": "222"}},
            "revision",
        )
        self.assertEqual(records, rebuilt)
        self.assertEqual(report["unresolved"], [])

    def test_shared_name_and_code_do_not_merge_two_universities(self):
        base = [
            {"value": "hcm", "label": "University of Science", "code": "SCI"},
            {"value": "hn", "label": "University of Science", "code": "SCI"},
        ]
        records, report = build_catalogue(
            base,
            [],
            [{"domain": "science.edu.vn", "names": ["University of Science"]}],
            {},
            "revision",
        )
        self.assertEqual(len(records), 2)
        self.assertEqual(len(report["unresolved"]), 1)
        self.assertTrue(all(not r["domains"] for r in records))

    def test_shared_and_out_of_scope_domains_are_held_for_review(self):
        swot = [
            {"domain": "province.edu.vn", "names": ["Schools", ".group"]},
            {"domain": "person.edu.vn", "names": ["Example Person"]},
        ]
        records, report = build_catalogue([], [], swot, {}, "revision")
        self.assertEqual(records, [])
        self.assertEqual(len(report["unresolved"]), 2)

    def test_high_school_added_without_fabricating_location_or_abbreviation(self):
        swot = [
            {
                "domain": "ptnk.edu.vn",
                "names": [
                    "VNU-HCM High School for the Gifted",
                    "Trường Phổ Thông Năng Khiếu, ĐHQG-HCM",
                ],
            }
        ]
        records, _ = build_catalogue(
            [], [], swot, {"add_domains": ["ptnk.edu.vn"]}, "revision"
        )
        self.assertEqual(records[0]["label"], "Trường Phổ Thông Năng Khiếu, ĐHQG-HCM")
        self.assertEqual(records[0]["type"], "THPT")
        self.assertEqual(records[0]["location"], "")
        self.assertEqual(records[0]["shortName"], "")
        self.assertEqual(records[0]["domains"], ["ptnk.edu.vn"])

    def test_unmatched_swot_school_is_a_candidate_until_explicitly_included(self):
        records, report = build_catalogue(
            [],
            [],
            [{"domain": "unknown.edu.vn", "names": ["Unknown University"]}],
            {},
            "revision",
        )
        self.assertEqual(records, [])
        self.assertEqual(report["unresolved"][0]["domain"], "unknown.edu.vn")

    def test_changed_admissions_code_reuses_a_unique_name_match(self):
        base = [{"value": "123", "label": "Example University", "code": "OLD"}]
        records, _ = build_catalogue(
            base,
            [{"Id": "new-code", "MA": "NEW", "TEN_DON_VI": "Example University"}],
            [],
            {},
            "revision",
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["value"], "123")
        self.assertEqual(records[0]["code"], "NEW")
        self.assertIn("OLD", records[0]["aliases"])
