import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import citation_check as cc  # noqa: E402

ARXIV_OK = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/1706.03762v7</id>
    <title>Attention Is All You
      Need</title>
    <summary>The dominant sequence transduction models are based on complex
      recurrent or convolutional neural networks.</summary>
  </entry>
</feed>"""

ARXIV_ERROR = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/api/errors#incorrect_id_format_for_9999.99999</id>
    <title>Error</title>
    <summary>incorrect id format for 9999.99999</summary>
  </entry>
</feed>"""

OPENALEX_OK = json.dumps({
    "display_name": "Deep learning",
    "abstract_inverted_index": {"Deep": [0], "learning": [1], "allows": [2], "computational": [3], "models": [4]},
})


def make_fetcher(routes):
    calls = []

    def fetch(url):
        calls.append(url)
        for prefix, resp in routes.items():
            if url.startswith(prefix):
                if isinstance(resp, Exception):
                    raise resp
                return resp
        return cc.Response(404, "")

    fetch.calls = calls
    return fetch


def test_classify():
    assert cc.classify("10.1038/NATURE14539") == ("doi", "10.1038/nature14539")
    assert cc.classify("https://doi.org/10.1038/nature14539.") == ("doi", "10.1038/nature14539")
    assert cc.classify("arXiv:1706.03762v5") == ("arxiv", "1706.03762")
    assert cc.classify("https://arxiv.org/pdf/1706.03762v2.pdf") == ("arxiv", "1706.03762")
    assert cc.classify("1706.03762") == ("arxiv", "1706.03762")
    assert cc.classify("hep-th/9901001") == ("arxiv", "hep-th/9901001")
    assert cc.classify("W2919115771") == ("openalex", "W2919115771")
    assert cc.classify("https://openalex.org/W2919115771") == ("openalex", "W2919115771")
    assert cc.classify("https://example.com/page") == ("url", "https://example.com/page")
    assert cc.classify("Smith et al. 2020") == ("unknown", None)


def test_extract_refs_dedupes_and_skips_overlaps():
    text = (
        "See arXiv:1706.03762 and https://arxiv.org/abs/1706.03762v2. "
        "Also (https://doi.org/10.1038/nature14539), 10.1038/nature14539, "
        "and https://openml.org/t/31."
    )
    assert cc.extract_refs(text) == ["arXiv:1706.03762", "10.1038/nature14539", "https://openml.org/t/31"]


def test_arxiv_resolves_and_quote_found_despite_whitespace_and_case():
    fetch = make_fetcher({"https://export.arxiv.org/": cc.Response(200, ARXIV_OK)})
    r = cc.check_ref({"ref": "arXiv:1706.03762", "quote": "based on complex recurrent  OR convolutional neural networks"}, fetch)
    assert r.resolved is True and r.title == "Attention Is All You Need"
    assert r.quote_status == "found" and r.checked_text == "abstract"


def test_arxiv_error_entry_is_unresolvable():
    fetch = make_fetcher({"https://export.arxiv.org/": cc.Response(200, ARXIV_ERROR)})
    r = cc.check_ref({"ref": "arXiv:9999.99999", "quote": "anything"}, fetch)
    assert r.resolved is False and r.quote_status == "unchecked"


def test_doi_falls_back_to_crossref_and_reports_missing_quote():
    crossref = json.dumps({"message": {"title": ["Deep learning"], "abstract": "<jats:p>Deep learning allows models</jats:p>"}})
    fetch = make_fetcher({
        "https://api.openalex.org/": cc.Response(404, ""),
        "https://api.crossref.org/": cc.Response(200, crossref),
    })
    r = cc.check_ref({"ref": "10.1038/nature14539", "quote": "a sentence that is not there"}, fetch)
    assert r.resolved is True and r.resolver == "crossref"
    assert r.quote_status == "not_in_available_text"


def test_doi_unresolvable_when_both_resolvers_404():
    fetch = make_fetcher({})
    r = cc.check_ref({"ref": "10.9999/made.up.2026"}, fetch)
    assert r.resolved is False and r.quote_status == "no_quote"


def test_openalex_abstract_reconstruction():
    fetch = make_fetcher({"https://api.openalex.org/": cc.Response(200, OPENALEX_OK)})
    r = cc.check_ref({"ref": "10.1038/nature14539", "quote": "allows computational models"}, fetch)
    assert r.resolver == "openalex" and r.quote_status == "found"


def test_network_error_is_not_a_failed_resolution():
    fetch = make_fetcher({"https://export.arxiv.org/": ConnectionError("proxy denied")})
    r = cc.check_ref({"ref": "arXiv:1706.03762", "quote": "x"}, fetch)
    assert r.resolved is None and r.error and r.quote_status == "unchecked"


def test_server_error_is_not_a_failed_resolution():
    fetch = make_fetcher({"https://api.openalex.org/": cc.Response(503, ""), "https://api.crossref.org/": cc.Response(503, "")})
    assert cc.check_ref({"ref": "10.1038/nature14539"}, fetch).resolved is None


def test_fulltext_is_preferred_over_abstract(tmp_path):
    body = tmp_path / "paper.txt"
    body.write_text("Section 3. The model reaches 28.4 BLEU on WMT 2014.")
    fetch = make_fetcher({"https://export.arxiv.org/": cc.Response(200, ARXIV_OK)})
    r = cc.check_ref({"ref": "1706.03762", "quote": "reaches 28.4 BLEU", "fulltext_path": str(body)}, fetch)
    assert r.quote_status == "found" and r.checked_text == "fulltext"


def test_summary_denominators():
    fetch = make_fetcher({
        "https://export.arxiv.org/api/query?id_list=1706.03762": cc.Response(200, ARXIV_OK),
        "https://export.arxiv.org/api/query?id_list=2001.00001": ConnectionError("down"),
    })
    report = cc.run([
        {"ref": "arXiv:1706.03762", "quote": "recurrent or convolutional"},  # resolved, quote found
        {"ref": "arXiv:1706.03762", "quote": "not in the abstract"},         # resolved, quote missing
        {"ref": "10.9999/fake"},                                             # unresolvable
        {"ref": "arXiv:2001.00001"},                                         # network error
        {"ref": "Smith 2020"},                                               # unknown, unresolvable
    ], fetch)
    s = report["summary"]
    assert s["references_total"] == 5
    assert s["check_errors"] == 1
    assert s["references_checked"] == 4
    assert s["unresolvable"] == 2 and s["unresolvable_rate"] == 0.5
    assert s["quote_found"] == 1 and s["quote_not_in_available_text"] == 1
    assert s["unsupported_quote_rate"] == 0.5


def test_cli_on_markdown(tmp_path, monkeypatch, capsys):
    report_md = tmp_path / "final_report.md"
    report_md.write_text("Evidence: arXiv:1706.03762.")
    monkeypatch.setattr(cc, "default_fetcher", make_fetcher({"https://export.arxiv.org/": cc.Response(200, ARXIV_OK)}))
    monkeypatch.setattr(cc.run, "__defaults__", (cc.default_fetcher,))
    out = tmp_path / "citations.json"
    assert cc.main([str(report_md), "-o", str(out)]) == 0
    data = json.loads(out.read_text())
    assert data["summary"]["resolvable"] == 1
    assert "1 refs: 1 resolved" in capsys.readouterr().err
