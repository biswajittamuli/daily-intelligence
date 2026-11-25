"""v5: government / PSU / examination source crawling — parsing, notices, dedup and calendars.

Everything here is pure or store-local: no network, no model.
"""
from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from app.memory.store import Store
from app.services.gov_crawler import (backoff_hours, build_notice, candidates, classify_link, exam_events_from,
                                      is_junk_title, links_fingerprint, listing_links, parse_exam_calendar, parse_rss)
from app.services.gov_sources import GovSource

TODAY = date(2026, 11, 16)
SOURCE = GovSource("ntpc", "NTPC", "NTPC Limited", "psu", "https://www.ntpc.co.in/careers")
LISTING = "https://www.ntpc.co.in/careers"

NOTICE_TEXT = """NTPC LIMITED
Advt. No. 07/2026
Recruitment of Graduate Engineers (Executive Trainee)
Total posts: 120
Upper age limit is 30 years as on 01.01.2027. Age relaxation: OBC-NCL candidates by 3 years.
Essential Qualification: B.Tech in Computer Science / Information Technology with minimum 60% marks.
GATE 2026 score in CS paper is mandatory.
Pay scale: Rs. 50000-160000
Online applications open on 01.12.2026 and the last date for submission is 31.01.2027.
"""


class ListingParsingTests(unittest.TestCase):
    HTML = """<html><body><table>
      <tr><td>Advt. No. 07/2026 - Recruitment of Graduate Engineers</td>
          <td><a href="/docs/advt-07-2026.pdf">Click here</a></td></tr>
      <tr><td>Corrigendum to Advt. No. 07/2026</td>
          <td><a href="/docs/corrigendum-07.pdf">English</a></td></tr>
      <tr><td>Recruitment of Management Trainees 2026</td>
          <td><a href="/notice/mt-2026">Click here</a></td></tr>
      <tr><td>Tender for supply of laptops</td><td><a href="/tender.pdf">Download</a></td></tr>
      <tr><td>Annual Report 2025-26</td><td><a href="/annual-report.pdf">PDF</a></td></tr>
      <tr><td><a href="https://facebook.com/ntpc">Facebook</a></td></tr>
      <tr><td>Recruitment System in NTPC</td><td><a href="/recruitment-system">Click here</a></td></tr>
    </table></body></html>"""

    def test_row_context_names_a_notice_labelled_click_here(self):
        links = listing_links(LISTING, self.HTML)
        first = next(link for link in links if link["url"].endswith("advt-07-2026.pdf"))
        self.assertEqual(first["context"], "Advt. No. 07/2026 - Recruitment of Graduate Engineers")
        self.assertEqual(first["text"], "Click here")

    def test_classification(self):
        self.assertEqual(classify_link("Corrigendum to Advt. No. 07/2026"), "corrigendum")
        self.assertEqual(classify_link("Recruitment of Graduate Engineers 2026"), "advertisement")
        self.assertEqual(classify_link("Admit card for CBT 2026"), "admit_card")
        self.assertEqual(classify_link("Result of written examination"), "result")
        self.assertEqual(classify_link("Annual Report 2025-26"), "other")
        self.assertEqual(classify_link("Tender for laptops"), "other")

    def test_candidates_keep_notices_and_drop_tenders_navigation_and_social_links(self):
        found = candidates(SOURCE, listing_links(LISTING, self.HTML))
        urls = {item["url"] for item in found}
        self.assertIn("https://www.ntpc.co.in/docs/advt-07-2026.pdf", urls)
        self.assertIn("https://www.ntpc.co.in/docs/corrigendum-07.pdf", urls)
        self.assertIn("https://www.ntpc.co.in/notice/mt-2026", urls)
        self.assertFalse(any("tender" in url or "annual-report" in url or "facebook" in url for url in urls))
        self.assertFalse(any(url.endswith("/recruitment-system") for url in urls))
        classes = {item["url"]: item["doc_class"] for item in found}
        self.assertEqual(classes["https://www.ntpc.co.in/docs/corrigendum-07.pdf"], "corrigendum")

    def test_apply_link_is_marked(self):
        html = """<table><tr><td>Recruitment of Graduate Engineers 2026</td>
                  <td><a href="/apply">Apply Online</a></td></tr></table>"""
        found = candidates(SOURCE, listing_links(LISTING, html))
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["apply"], "1")

    def test_hindi_and_duplicate_links_are_dropped(self):
        html = """<table>
          <tr><td>Recruitment of Graduate Engineers 2026</td><td><a href="/a.pdf">Click here</a></td></tr>
          <tr><td>Recruitment of Graduate Engineers 2026</td><td><a href="/a.pdf">विज्ञापन</a></td></tr>
          <tr><td>पदों पर भर्ती 2026</td><td><a href="/hindi.pdf">हिंदी</a></td></tr>
        </table>"""
        found = candidates(SOURCE, listing_links(LISTING, html))
        self.assertEqual([item["url"] for item in found], ["https://www.ntpc.co.in/a.pdf"])

    def test_fingerprint_does_not_depend_on_link_order(self):
        one = [{"url": "https://a.in/1", "title": "One"}, {"url": "https://a.in/2", "title": "Two"}]
        self.assertEqual(links_fingerprint(one), links_fingerprint(list(reversed(one))))
        self.assertNotEqual(links_fingerprint(one), links_fingerprint(one[:1]))


class NoticeBuildTests(unittest.TestCase):
    def notice(self, **overrides):
        return build_notice(SOURCE, url="https://www.ntpc.co.in/docs/advt-07-2026.pdf",
                            title="Advt. No. 07/2026 Recruitment of Graduate Engineers", text=NOTICE_TEXT,
                            listing_url=LISTING, today=TODAY, **overrides)

    def test_metadata_row_title_is_not_used_as_the_headline(self):
        junk = ('1 {"meta_value":"Uttarakhand Public Service Commission"} 06-11-2026 06-11-2026 '
                '06-11-2026 23-11-2026 Click here')
        self.assertTrue(is_junk_title(junk))
        self.assertFalse(is_junk_title("Advt. No. 07/2026 Recruitment of Graduate Engineers"))
        self.assertFalse(is_junk_title("Recruitment of Assistant Engineers 2026"))
        source = GovSource("ukpsc", "UKPSC", "Uttarakhand Public Service Commission", "state_psc", LISTING)
        text = ("UTTARAKHAND PUBLIC SERVICE COMMISSION\nAdvertisement No. 12/2026\n"
                "Recruitment of Assistant Engineer (Civil)\nTotal posts: 45\n"
                "Last date for submission of online application: 23.11.2026\n")
        notice = build_notice(source, url="https://psc.uk.gov.in/public/uploads/recruitment/901380456.pdf",
                              title=junk, text=text, listing_url=LISTING, today=TODAY)
        self.assertEqual(notice["post_name"], "Recruitment of Assistant Engineer (Civil)")
        self.assertEqual(notice["advertisement_number"], "12/2026")
        self.assertEqual(notice["closing_date"], "2026-11-23")
        self.assertEqual(notice["document_type"], "recruitment_advertisement")
        # A PDF whose title and text state nothing a notification states stays an official document, not an ad.
        opaque = build_notice(source, url="https://psc.uk.gov.in/public/uploads/recruitment/1.pdf", title=junk,
                              text="foKfIr\nvfHkys[k lR;kiu fnukad 23-11-2026", listing_url=LISTING, today=TODAY)
        self.assertIsNone(opaque["post_name"])
        self.assertEqual(opaque["document_type"], "official_document")

    def test_fields_are_copied_from_the_notification(self):
        notice = self.notice()
        self.assertEqual(notice["organization"], "NTPC Limited")
        self.assertEqual(notice["advertisement_number"], "07/2026")
        self.assertEqual(notice["post_name"], "Recruitment of Graduate Engineers")
        self.assertEqual(notice["vacancies"], "120")
        self.assertEqual(notice["opening_date"], "2026-12-01")
        self.assertEqual(notice["closing_date"], "2027-01-31")
        self.assertEqual(notice["age_max"], 30)
        self.assertEqual(notice["min_percentage"], 60.0)
        self.assertEqual(notice["gate_required"], 1)
        self.assertEqual(notice["gate_paper"], "CS")
        self.assertEqual(notice["status"], "open")
        self.assertEqual(notice["document_type"], "recruitment_advertisement")
        self.assertTrue(notice["official_source"])
        self.assertEqual(notice["dedup_key"], "ntpc limited|072026|recruitment of graduate engineers")

    def test_requirements_and_evidence_quote_the_clauses(self):
        notice = self.notice()
        self.assertEqual(notice["requirements"]["age_relaxation"]["years"], {"OBC-NCL": 3})
        self.assertEqual(notice["requirements"]["qualification"]["branches"], ["cs", "it"])
        self.assertTrue(notice["requirements"]["gate"]["required"])
        fields = {item["field"] for item in notice["evidence"]}
        self.assertTrue({"advertisement_number", "age", "qualification", "gate"} <= fields)
        self.assertTrue(all(item["source_url"].endswith("advt-07-2026.pdf") for item in notice["evidence"]))

    def test_past_closing_date_is_closed(self):
        notice = self.notice()
        late = build_notice(SOURCE, url=notice["url"], title=notice["post_name"] or "notice",
                            text=NOTICE_TEXT.replace("31.01.2027", "31.01.2026")
                            .replace("01.12.2026", "01.11.2025"), today=TODAY)
        self.assertEqual(late["status"], "closed")

    def test_application_url_is_kept_only_when_stated(self):
        self.assertIsNone(self.notice()["application_url"])
        self.assertEqual(self.notice(application_url="https://careers.ntpc.co.in/apply")["application_url"],
                         "https://careers.ntpc.co.in/apply")

    def test_exam_events_carry_their_evidence_and_tentative_marking(self):
        notice = self.notice()
        events = exam_events_from(notice, SOURCE)
        kinds = {(event["event_type"], event["event_date"]) for event in events}
        self.assertIn(("application_open", "2026-12-01"), kinds)
        self.assertIn(("application_close", "2027-01-31"), kinds)
        tentative = exam_events_from(notice, SOURCE, [{"exam_name": notice["post_name"], "event_type": "exam",
                                                       "event_date": "2027-03-01",
                                                       "evidence": "Tentative date of examination: 01.03.2027"}])
        self.assertEqual(tentative[-1]["date_status"], "tentative")


class NoticeStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def parent(self):
        notice, created = self.store.save_gov_notice(build_notice(
            SOURCE, url="https://www.ntpc.co.in/docs/advt-07-2026.pdf",
            title="Advt. No. 07/2026 Recruitment of Graduate Engineers", text=NOTICE_TEXT,
            listing_url=LISTING, today=TODAY))
        self.assertTrue(created)
        return notice

    def test_corrigendum_updates_the_notice_instead_of_duplicating_it(self):
        from app.services.gov_crawler import GovCrawler
        original = self.parent()
        crawler = GovCrawler(self.store, None, today=TODAY)
        text = ("NTPC LIMITED\nCorrigendum to Advt. No. 07/2026\n"
                "The last date for submission of online applications has been extended to 28.02.2027.")
        counts = {"notices_updated": 0}
        notice_id = crawler._apply_corrigendum(SOURCE, {"url": "https://www.ntpc.co.in/docs/corrigendum-07.pdf",
                                                        "title": "Corrigendum to Advt. No. 07/2026"},
                                               text, counts, "NTPC Limited")
        self.assertEqual(notice_id, original["id"])
        self.assertEqual(counts["notices_updated"], 1)
        updated = self.store.notice(original["id"])
        self.assertEqual(updated["closing_date"], "2027-02-28")
        self.assertEqual(updated["status"], "open")
        self.assertEqual(len(self.store.notices()), 1)
        history = updated["history"]
        self.assertEqual(history[-1]["change"], "corrigendum")
        self.assertTrue(any(item.get("field") == "closing_date" and item.get("to") == "2027-02-28"
                            for item in history))
        # The corrigendum never replaces the original notification's link or text.
        self.assertEqual(updated["document_url"], original["document_url"])
        self.assertEqual(updated["notification_text"], original["notification_text"])

    def test_a_corrigendum_alone_is_not_stored_as_a_notice(self):
        from app.services.gov_crawler import GovCrawler
        crawler = GovCrawler(self.store, None, today=TODAY)
        counts = {"notices_updated": 0}
        notice_id = crawler._apply_corrigendum(
            SOURCE, {"url": "https://www.ntpc.co.in/docs/corrigendum-99.pdf",
                     "title": "Corrigendum to Advt. No. 99/2026"},
            "Corrigendum to Advt. No. 99/2026. The date is extended to 28.02.2027.", counts, "NTPC Limited")
        self.assertIsNone(notice_id)
        self.assertEqual(self.store.notices(), [])
        self.assertEqual(counts["notices_updated"], 0)


class FeedAndCalendarTests(unittest.TestCase):
    def test_rss_and_atom_items(self):
        rss = ("<?xml version='1.0'?><rss><channel><item><title>NTPC recruitment 2026</title>"
               "<link>https://ntpc.co.in/n.xml</link><pubDate>Mon, 16 Nov 2026 10:00:00 GMT</pubDate>"
               "<description>&lt;p&gt;Engineer posts&lt;/p&gt;</description></item></channel></rss>")
        item = parse_rss(rss)[0]
        self.assertEqual(item["title"], "NTPC recruitment 2026")
        self.assertEqual(item["summary"], "Engineer posts")
        atom = ("<feed xmlns='http://www.w3.org/2005/Atom'><entry><title>UPSC notice</title>"
                "<link href='https://upsc.gov.in/n'/><updated>2026-11-16T10:00:00Z</updated></entry></feed>")
        self.assertEqual(parse_rss(atom)[0]["url"], "https://upsc.gov.in/n")
        self.assertEqual(parse_rss("<rss><channel>"), [])

    def test_calendar_reads_columns_from_the_header_row(self):
        text = ("Examination\tNotification\tApplication Start\tLast Date\tExam Date\n"
                "GATE 2027\t05.08.2026\t10.08.2026\t25.09.2026\t07.02.2027\n")
        events = parse_exam_calendar(text)
        self.assertEqual([(event["event_type"], event["event_date"]) for event in events],
                         [("notification", "2026-08-05"), ("application_open", "2026-08-10"),
                          ("application_close", "2026-09-25"), ("exam", "2027-02-07")])
        self.assertTrue(all(event["exam_name"] == "GATE 2027" for event in events))

    def test_calendar_skips_rows_whose_dates_cannot_be_mapped(self):
        text = ("Examination\tNotification\tApplication Start\tLast Date\tExam Date\n"
                "GATE 2027\t05.08.2026\t\t25.09.2026\t07.02.2027\n")
        self.assertEqual(parse_exam_calendar(text), [])

    def test_backoff(self):
        self.assertEqual(backoff_hours(24, 0), 24)
        self.assertEqual(backoff_hours(24, 1), 24)
        self.assertEqual(backoff_hours(24, 2), 48)
        self.assertEqual(backoff_hours(24, 50), 24 * 7)


if __name__ == "__main__":
    unittest.main()
