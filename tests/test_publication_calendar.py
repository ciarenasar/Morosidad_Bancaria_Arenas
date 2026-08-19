import unittest
from datetime import date

from morosidad_bancaria.data.publication_calendar import (
    audit_calendar,
    combine_entries,
    parse_cmf_press,
    parse_sbif_archive,
)


class PublicationParsingTests(unittest.TestCase):
    def test_parses_current_cmf_article(self):
        html = b"""
        <article><time><span>30</span><span>jul</span><span>2026</span></time>
        <h3><a href="w4-article-1.html">CMF informa el desempe\xc3\xb1o de bancos y
        cooperativas supervisadas a junio de 2026</a></h3></article>
        """
        entries = parse_cmf_press(html, "https://www.cmfchile.cl/portal/prensa/615/")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].observation_date, date(2026, 6, 1))
        self.assertEqual(entries[0].forecast_issue_date, date(2026, 7, 30))

    def test_parses_legacy_sbif_row(self):
        html = b"""
        <table><tr><td><p>30/05/2019</p><h2><a href="?id=1">Resumen del
        Desempe\xc3\xb1o de Bancos y Cooperativas a abril de 2019</a></h2></td></tr></table>
        """
        entries = parse_sbif_archive(html, "https://example.test/Noticia")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].observation_date, date(2019, 4, 1))
        self.assertEqual(entries[0].forecast_issue_date, date(2019, 5, 30))

    def test_audit_reports_missing_month(self):
        entry = parse_cmf_press(
            (
                b"<article><time>30 jul 2026</time><h3>"
                b"Desempe\xc3\xb1o de bancos a junio de 2026</h3></article>"
            ),
            "https://example.test/",
        )[0]
        report = audit_calendar(
            combine_entries([entry]),
            [date(2026, 5, 1), date(2026, 6, 1)],
        )
        self.assertEqual(report.missing_months, ["2026-05-01"])


if __name__ == "__main__":
    unittest.main()
