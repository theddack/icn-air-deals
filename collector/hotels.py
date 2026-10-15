"""수집 대상 호텔·숙박 브랜드 목록. 형식은 airlines.py와 같다.

name    화면에 표시할 이름이자 뉴스 검색어
aliases 기사 제목에서 이 브랜드를 알아보는 표기 (긴 것부터 매칭)
search  뉴스 검색어를 name 대신 여러 개로 쓸 때 (선택)
kind    hotel (호텔·리조트 운영사) | platform (숙박 예약 플랫폼·여행사) | campaign (정부·지자체 할인 행사)

공식 페이지 링크(official_url)는 주소 응답을 확인한 뒤에만 넣는다 (2026-10-15, 예약 플랫폼·여행사 11곳).
항공권 행사 기사 제목에 플랫폼·여행사가 나오면 화면에 "기사에 나온 판매처"로 이 링크를 보여준다.
"""

HOTELS = [
    # 호텔·리조트
    {"id": "h-paradise", "name": "파라다이스", "aliases": ["파라다이스시티", "파라다이스호텔", "파라다이스"], "kind": "hotel"},
    {"id": "h-lotte", "name": "롯데호텔", "aliases": ["롯데호텔앤리조트", "롯데호텔", "롯데리조트", "시그니엘", "L7"], "kind": "hotel"},
    {"id": "h-shilla", "name": "신라호텔", "aliases": ["신라호텔", "신라스테이", "서울신라"], "search": ["신라호텔", "신라스테이"], "kind": "hotel"},
    {"id": "h-josun", "name": "조선호텔앤리조트", "aliases": ["조선호텔앤리조트", "웨스틴 조선", "그랜드 조선", "조선 팰리스", "레스케이프", "그래비티"], "search": ["조선호텔앤리조트", "그랜드 조선"], "kind": "hotel"},
    {"id": "h-walkerhill", "name": "워커힐", "aliases": ["워커힐"], "kind": "hotel"},
    {"id": "h-sono", "name": "소노", "aliases": ["소노인터내셔널", "소노호텔앤리조트", "소노캄", "소노벨", "소노"], "search": ["소노인터내셔널", "소노호텔앤리조트"], "kind": "hotel"},
    {"id": "h-hanwha", "name": "한화리조트", "aliases": ["한화호텔앤드리조트", "한화리조트", "더 플라자"], "search": ["한화리조트", "한화호텔앤드리조트"], "kind": "hotel"},
    {"id": "h-kensington", "name": "켄싱턴호텔앤리조트", "aliases": ["켄싱턴"], "search": ["켄싱턴호텔"], "kind": "hotel"},
    {"id": "h-inspire", "name": "인스파이어", "aliases": ["인스파이어 엔터테인먼트 리조트", "인스파이어"], "kind": "hotel"},
    {"id": "h-marriott", "name": "메리어트", "aliases": ["메리어트 본보이", "메리어트"], "kind": "hotel"},
    {"id": "h-hilton", "name": "힐튼", "aliases": ["힐튼"], "kind": "hotel"},
    {"id": "h-hyatt", "name": "하얏트", "aliases": ["하얏트"], "kind": "hotel"},
    {"id": "h-ihg", "name": "IHG", "aliases": ["IHG", "인터컨티넨탈"], "search": ["IHG 호텔", "인터컨티넨탈"], "kind": "hotel"},
    {"id": "h-accor", "name": "아코르", "aliases": ["아코르", "노보텔", "소피텔", "이비스", "머큐어", "페어몬트"], "search": ["아코르", "노보텔"], "kind": "hotel"},
    # 숙박 예약 플랫폼·여행사
    {"id": "h-yeogi", "name": "여기어때", "aliases": ["여기어때"], "official_url": "https://www.yeogi.com/", "kind": "platform"},
    {"id": "h-nol", "name": "놀(야놀자)", "aliases": ["놀유니버스", "야놀자", "NOL"], "search": ["야놀자", "놀유니버스"], "official_url": "https://nol.yanolja.com/", "kind": "platform"},
    {"id": "h-agoda", "name": "아고다", "aliases": ["아고다"], "official_url": "https://www.agoda.com/ko-kr/", "kind": "platform"},
    {"id": "h-tripcom", "name": "트립닷컴", "aliases": ["트립닷컴"], "official_url": "https://kr.trip.com/", "kind": "platform"},
    {"id": "h-expedia", "name": "익스피디아", "aliases": ["익스피디아"], "official_url": "https://www.expedia.co.kr/", "kind": "platform"},
    {"id": "h-hotelscom", "name": "호텔스닷컴", "aliases": ["호텔스닷컴"], "official_url": "https://kr.hotels.com/", "kind": "platform"},
    {"id": "h-booking", "name": "부킹닷컴", "aliases": ["부킹닷컴"], "official_url": "https://www.booking.com/index.ko.html", "kind": "platform"},
    {"id": "h-myrealtrip", "name": "마이리얼트립", "aliases": ["마이리얼트립"], "official_url": "https://www.myrealtrip.com/", "kind": "platform"},
    {"id": "h-tripbtoz", "name": "트립비토즈", "aliases": ["트립비토즈"], "official_url": "https://www.tripbtoz.com/", "kind": "platform"},
    {"id": "h-hanatour", "name": "하나투어", "aliases": ["하나투어"], "official_url": "https://www.hanatour.com/", "kind": "platform"},
    {"id": "h-modetour", "name": "모두투어", "aliases": ["모두투어"], "official_url": "https://www.modetour.com/", "kind": "platform"},
    # 정부 할인 행사
    {"id": "h-stayfesta", "name": "숙박세일 페스타", "aliases": ["숙박세일 페스타", "숙박세일페스타"], "kind": "campaign"},
]

BY_ID = {h["id"]: h for h in HOTELS}
