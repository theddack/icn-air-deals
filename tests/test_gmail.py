"""Gmail 발신자 → 항공사 판별, 발신 인증. 주소와 헤더는 형식만 흉내 낸 예시다(실제 수신 메일 아님)."""

import unittest

from collector.sources.gmail_imap import SEARCH_DOMAINS, airline_of, authenticated, decode, search_query


class TestAirlineOf(unittest.TestCase):
    def check(self, header, expected, basis="domain"):
        name, _, how = airline_of(header)
        self.assertEqual((name, how if name else None), (expected, basis if expected else None), header)

    def test_official_domain_and_subdomain(self):
        self.check('"제주항공" <news@jejuair.net>', "제주항공")
        self.check("Air Busan <noreply@mail.airbusan.com>", "에어부산")

    def test_core_name_on_other_tld(self):
        self.check("Japan Airlines <info@email.jal.com>", "일본항공")
        self.check("China Eastern <promo@ceair.com>", "중국동방항공")  # 공식 사이트는 kr.ceair.com
        self.check("Air Macau <news@ec.airmacau.com.cn>", "에어마카오")

    def test_extra_domains(self):
        self.check("HK Express <hello@news.hkexpress.com>", "홍콩익스프레스")
        self.check("Spring Airlines <edm@mail.ch.com>", "춘추항공")
        self.check("KLM <news@infos-klm.com>", "KLM")

    def test_display_name_only_needs_verification(self):
        self.check('"아시아나항공" <event@asiana-mail.example>', "아시아나항공", basis="name")
        self.check('"대한항공" <promo@lookalike.example>', "대한항공", basis="name")

    def test_ascii_alias_needs_word_boundary(self):
        self.check("BANANA Shop <sale@banana-shop.example>", None)

    def test_short_core_does_not_match_unrelated_label(self):
        self.check("Someone <x@aa.example.org>", None)
        self.check("Someone <x@ch.example.org>", None)

    def test_non_airline(self):
        name, domain, basis = airline_of('"은행 알림" <notice@bank.example.co.kr>')
        self.assertEqual((name, domain, basis), (None, "bank.example.co.kr", None))

    def test_encoded_header(self):
        header = "=?UTF-8?B?7KeE7JeQ7Ja0?= <promo@notice.example>"  # 진에어
        self.assertEqual(decode(header).split(" <")[0], "진에어")
        self.check(header, "진에어", basis="name")


GOOD = ("mx.google.com;\r\n       dkim=pass header.i=@email.finnair.com header.s=s1 header.b=abc;\r\n"
        "       spf=pass (google.com: domain of bounce@email.finnair.com) smtp.mailfrom=bounce@email.finnair.com;\r\n"
        "       dmarc=pass (p=REJECT sp=REJECT dis=NONE) header.from=finnair.com")


class TestAuthenticated(unittest.TestCase):
    def test_gmail_dkim_or_dmarc_pass_for_same_org(self):
        self.assertTrue(authenticated([GOOD], "email.finnair.com"))
        self.assertTrue(authenticated(["mx.google.com; dmarc=pass (p=NONE) header.from=jejuair.net"], "jejuair.net"))

    def test_signature_from_other_domain_fails(self):
        # 대행사 도메인으로 서명됐고 DMARC는 실패 → 항공사 메일로 인증하지 않는다
        h = "mx.google.com; dkim=pass header.i=@sendgrid.example; dmarc=fail header.from=jejuair.net"
        self.assertFalse(authenticated([h], "jejuair.net"))

    def test_header_not_added_by_gmail_is_ignored(self):
        self.assertFalse(authenticated(["evil.example; dkim=pass header.d=jejuair.net"], "jejuair.net"))

    def test_missing(self):
        self.assertFalse(authenticated([], "jejuair.net"))
        self.assertFalse(authenticated([GOOD], ""))


class TestSearch(unittest.TestCase):
    def test_query_is_limited_to_airline_domains(self):
        q = search_query(30)
        self.assertTrue(q.startswith("newer_than:30d from:("))
        for d in ("jejuair.net", "ceair.com", "jal.co.jp", "jal.com", "airmacau.com.cn", "infos-klm.com"):
            self.assertIn(d, SEARCH_DOMAINS)
        self.assertNotIn("kr.ceair.com", SEARCH_DOMAINS)  # 하위 도메인은 등록 도메인으로 묶는다


if __name__ == "__main__":
    unittest.main()
