import unittest
from literature_helper import summarize, LiteratureHelper, HelperError

class IeeeMetadataTests(unittest.TestCase):
    def test_crossref_primary_article_is_preserved_without_query(self):
        paper = summarize({"DOI": "10.1109/ACCESS.2022.3181725",
                           "resource": {"primary": {"URL": "https://ieeexplore.ieee.org/document/9792260/?private=unused"}}})
        self.assertEqual(paper["publisher_article_url"], "https://ieeexplore.ieee.org/document/9792260/")
        self.assertNotIn("private", str(paper))

    def test_similar_domain_and_credentials_do_not_bind_article(self):
        for url in ["https://ieeexplore.ieee.org.evil.example/document/9792260",
                    "https://user:secret@ieeexplore.ieee.org/document/9792260",
                    "http://ieeexplore.ieee.org/document/9792260"]:
            self.assertNotIn("publisher_article_url", summarize({"resource": {"primary": {"URL": url}}}))

    def test_lookup_conflicting_doi_rejects_identity(self):
        class Client:
            def json(self, url): return {"message": {"DOI": "10.1000/wrong"}}
        with self.assertRaises(HelperError):
            LiteratureHelper(client=Client()).lookup("10.1000/expected")

if __name__ == "__main__":
    unittest.main()
