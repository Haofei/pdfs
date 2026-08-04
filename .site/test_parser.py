#!/usr/bin/env python3
"""Golden tests for the filename grammar in generate_manifest.py.

Every case here is a real filename from the repo, chosen to pin down an edge
of the grammar.  Run: python3 .site/test_parser.py
"""

import sys
import unittest

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from generate_manifest import (classify_type, included, parse_stem, strip_ext,
                               topics_for)


def parse_path(path):
    base = path.rsplit("/", 1)[-1]
    stem, ext, noext = strip_ext(base)
    parsed = parse_stem(stem)
    parsed["ext"] = ext
    parsed["noext"] = noext
    parsed["type"] = classify_type(stem, ext)
    return parsed


class TestGrammar(unittest.TestCase):

    def test_leading_year_with_arxiv_id(self):
        p = parse_path("Perfect Hashing/2019 - RecSplit - Minimal Perfect "
                       "Hashing via Recursive Splitting (1910.06416).pdf")
        self.assertEqual(p["year"], 2019)
        self.assertEqual(p["id"], "1910.06416")
        self.assertTrue(p["arxiv"])
        self.assertEqual(p["title"],
                         "RecSplit - Minimal Perfect Hashing via Recursive Splitting")

    def test_double_trailing_paren_keeps_inner_in_title(self):
        p = parse_path("Perfect Hashing/1992 - An Optimal Algorithm for "
                       "Generating Minimal Perfect Hash Functions (CHM92) "
                       "(10.1.1.51.5566).pdf")
        self.assertEqual(p["id"], "10.1.1.51.5566")
        self.assertEqual(p["year"], 1992)
        self.assertIn("(CHM92)", p["title"])

    def test_unicode_apostrophe_and_month_year_paren(self):
        p = parse_path("Intel 64 and IA-32 Architectures Software "
                       "Developer’s Manual V3 - Sept 2014 (325384-052US).pdf")
        self.assertEqual(p["year"], 2014)
        self.assertEqual(p["id"], "325384-052US")
        self.assertEqual(p["type"], "manual")
        self.assertIn("’", p["title"])
        self.assertEqual(p["quals"], "")  # date-ish qualifier consumed

    def test_hash_char_in_title(self):
        p = parse_path("Haskell vs. F# vs. Scala - A High-Level Language "
                       "Features and Parallelism Support Comparison (fhpc12).pdf")
        self.assertEqual(p["title"], "Haskell vs. F# vs. Scala")
        self.assertEqual(p["id"], "fhpc12")
        self.assertIsNone(p["year"])

    def test_double_extension(self):
        stem, ext, noext = strip_ext("Locks, Deadlocks and Synchronization - "
                                     "Windows Hardware and Driver Central (2006).pdf.docx")
        self.assertEqual(ext, "docx")
        self.assertFalse(noext)
        p = parse_stem(stem)
        self.assertEqual(p["year"], 2006)

    def test_uppercase_extension(self):
        stem, ext, _ = strip_ext("Star Schema Benchmark.PDF")
        self.assertEqual(ext, "pdf")
        self.assertEqual(stem, "Star Schema Benchmark")

    def test_extensionless_root_file(self):
        p = parse_path("Multi-core is Here - But How Do You Resolve Data "
                       "Bottlenecks in Native Code (AMD_Webcast_Jan_2008_MW)")
        self.assertEqual(p["ext"], "pdf")
        self.assertTrue(p["noext"])
        self.assertEqual(p["id"], "AMD_Webcast_Jan_2008_MW")
        self.assertEqual(p["type"], "slides")  # "Webcast"

    def test_extensionless_leading_year(self):
        p = parse_path("Perfect Hashing/2022 - Can Learned Models Replace "
                       "Hash Functions (p532-sabek)")
        self.assertEqual(p["year"], 2022)
        self.assertEqual(p["id"], "p532-sabek")
        self.assertTrue(p["noext"])

    def test_comma_month_paren_date(self):
        p = parse_path("5-Level Paging and 5-Level EPT - Intel - "
                       "Revision 1.0 (December, 2016).pdf")
        self.assertEqual(p["year"], 2016)
        self.assertIsNone(p["id"])
        self.assertEqual(p["quals"], "Intel · Revision 1.0")

    def test_year_first_comma_paren(self):
        p = parse_path("Oracle Bitmaps (1999, Jan) - Make a Little Bit Go a "
                       "Long Way (oracle-01_bitmap_1).doc")
        self.assertEqual(p["year"], 1999)  # via anywhere-in-stem fallback
        self.assertEqual(p["id"], "oracle-01_bitmap_1")
        self.assertEqual(p["ext"], "doc")

    def test_bare_year_qualifier_field(self):
        p = parse_path("Detours - Binary Interception of Win32 Functions - "
                       "1999 (huntusenixnt99).pdf")
        self.assertEqual(p["year"], 1999)
        self.assertEqual(p["id"], "huntusenixnt99")
        self.assertEqual(p["title"], "Detours")

    def test_root_leading_year_not_pure(self):
        p = parse_path("2018 CppCon Unwinding the Stack - Exploring how C++ "
                       "Exceptions work on Windows - James McNellis.pdf")
        self.assertEqual(p["year"], 2018)  # embedded, via fallback
        self.assertIn("James McNellis", p["quals"])

    def test_author_qualifier_paren_year(self):
        p = parse_path("Depth-First Search and Linear Graph Algorithms - "
                       "Tarjan (1972).pdf")
        self.assertEqual(p["year"], 1972)
        self.assertEqual(p["quals"], "Tarjan")
        self.assertIsNone(p["id"])
        self.assertEqual(p["type"], "paper")

    def test_venue_paren_becomes_id_year_from_fallback(self):
        p = parse_path("Repeating History Beyond ARIES - C. Mohan "
                       "(VLDB Conf, 1999).pdf")
        self.assertEqual(p["id"], "VLDB Conf, 1999")
        self.assertEqual(p["year"], 1999)

    def test_unparseable_fallback_never_crashes(self):
        p = parse_path("jargn10-thejargonfilever00038gut.txt")
        self.assertEqual(p["title"], "jargn10-thejargonfilever00038gut")
        self.assertIsNone(p["year"])
        self.assertEqual(p["type"], "text")

    def test_slides_qualifier_dropped_type_set(self):
        p = parse_path("100G Networking Technology Overview - Slides - "
                       "Toronto (August 2016).pdf")
        self.assertEqual(p["year"], 2016)
        self.assertEqual(p["type"], "slides")
        self.assertEqual(p["quals"], "Toronto")

    def test_arxiv_id_supplies_year(self):
        p = parse_path("Squares - A Fast Counter-Based RNG (2004.06278).pdf")
        self.assertTrue(p["arxiv"])
        self.assertEqual(p["year"], 2020)  # 2004.x = April 2020, not year 2004

    def test_exclusions(self):
        self.assertFalse(included("Inside IO Completion Ports_files/jquery.min.js"))
        self.assertFalse(included("x86asm.net/index.html"))
        self.assertFalse(included("README.md"))
        self.assertTrue(included("Star Schema Benchmark.PDF"))

    def test_perfect_hashing_folder_topic(self):
        self.assertIn("hashing",
                      topics_for("Perfect Hashing/1984 - Storing a Sparse Table "
                                 "with O(1) Worst Case Access Time (fks-perfecthash).pdf"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
