"""Gmail 발신자 → 항공사 판별. 주소는 형식만 흉내 낸 예시다(실제 수신 메일 아님)."""

import unittest

from collector.sources.gmail_imap import airline_of, decode


class TestAirlineOf(unittest.TestCase):
    def check(self, header, expected):
        self.assertEqual(airline_of(header)[0], expected, header)

    def test_official_domain_and_subdomain(self):
        self.check('"제주항공" <news@jejuair.net>', "제주항공")
        self.check("Air Busan <noreply@mail.airbusan.com>", "에어부산")

    def test_core_name_on_other_tld(self):
        # 공식 사이트 jal.co.jp, 메일은 email.jal.com에서 오는 경우
        self.check("Japan Airlines <info@email.jal.com>", "일본항공")
        self.check("China Eastern <promo@ceair.com>", "중국동방항공")  # 공식 사이트는 kr.ceair.com

    def test_extra_domains(self):
        self.check("HK Express <hello@news.hkexpress.com>", "홍콩익스프레스")
        self.check("Spring Airlines <edm@mail.ch.com>", "춘추항공")

    def test_display_name_alias(self):
        self.check('"아시아나항공" <event@asiana-mail.example>', "아시아나항공")
        self.check("KLM <news@info-mailer.example>", "KLM")

    def test_ascii_alias_needs_word_boundary(self):
        self.check("BANANA Shop <sale@banana-shop.example>", None)

    def test_short_core_does_not_match_unrelated_label(self):
        # aa.com(아메리칸)·ch.com(춘추)의 짧은 핵심 이름은 다른 도메인 라벨과 맞추지 않는다
        self.check("Someone <x@aa.example.org>", None)
        self.check("Someone <x@ch.example.org>", None)

    def test_non_airline(self):
        name, domain = airline_of('"은행 알림" <notice@bank.example.co.kr>')
        self.assertIsNone(name)
        self.assertEqual(domain, "bank.example.co.kr")

    def test_encoded_header(self):
        header = "=?UTF-8?B?7KeE7JeQ7Ja0?= <promo@notice.example>"  # 진에어
        self.assertEqual(decode(header).split(" <")[0], "진에어")
        self.check(header, "진에어")


if __name__ == "__main__":
    unittest.main()
