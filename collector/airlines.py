"""수집 대상 항공사 목록.

name    화면에 표시할 이름이자 뉴스 검색어
aliases 기사 제목에서 이 항공사를 알아보는 표기 (name 포함, 긴 것부터 매칭)
search  뉴스 검색어를 name 대신 여러 개로 쓸 때 (선택)
kind    domestic | foreign
"""

AIRLINES = [
    # 국내 FSC
    {"id": "koreanair", "name": "대한항공", "aliases": ["대한항공"], "kind": "domestic"},
    {"id": "asiana", "name": "아시아나항공", "aliases": ["아시아나항공", "아시아나"], "kind": "domestic"},
    # 국내 LCC
    {"id": "jejuair", "name": "제주항공", "aliases": ["제주항공"], "kind": "domestic"},
    {"id": "jinair", "name": "진에어", "aliases": ["진에어"], "kind": "domestic"},
    # 2026-09-10 티웨이항공 → 트리니티항공 사명 변경. 옛 이름 기사도 같은 항공사로 본다.
    {"id": "trinity", "name": "트리니티항공", "aliases": ["트리니티항공", "트리니티", "티웨이항공", "티웨이"],
     "search": ["트리니티항공", "티웨이항공"], "kind": "domestic"},
    {"id": "airbusan", "name": "에어부산", "aliases": ["에어부산"], "kind": "domestic"},
    {"id": "airseoul", "name": "에어서울", "aliases": ["에어서울"], "kind": "domestic"},
    {"id": "eastarjet", "name": "이스타항공", "aliases": ["이스타항공", "이스타"], "kind": "domestic"},
    {"id": "airpremia", "name": "에어프레미아", "aliases": ["에어프레미아"], "kind": "domestic"},
    {"id": "aerok", "name": "에어로케이", "aliases": ["에어로케이"], "kind": "domestic"},
    {"id": "parataair", "name": "파라타항공", "aliases": ["파라타항공", "파라타"], "kind": "domestic"},
    # 일본
    {"id": "jal", "name": "일본항공", "aliases": ["일본항공", "JAL"], "kind": "foreign"},
    {"id": "ana", "name": "전일본공수", "aliases": ["전일본공수", "ANA"], "kind": "foreign"},
    {"id": "peach", "name": "피치항공", "aliases": ["피치항공", "피치애비에이션"], "kind": "foreign"},
    {"id": "zipair", "name": "집에어", "aliases": ["집에어", "ZIPAIR"], "kind": "foreign"},
    # 중화권·몽골
    {"id": "cathay", "name": "캐세이퍼시픽", "aliases": ["캐세이퍼시픽"], "kind": "foreign"},
    {"id": "hkair", "name": "홍콩항공", "aliases": ["홍콩항공"], "kind": "foreign"},
    {"id": "eva", "name": "에바항공", "aliases": ["에바항공"], "kind": "foreign"},
    {"id": "chinaairlines", "name": "중화항공", "aliases": ["중화항공"], "kind": "foreign"},
    {"id": "starlux", "name": "스타럭스항공", "aliases": ["스타럭스항공", "스타럭스"], "kind": "foreign"},
    {"id": "tigertw", "name": "타이거에어", "aliases": ["타이거에어"], "kind": "foreign"},
    {"id": "chinaeastern", "name": "중국동방항공", "aliases": ["중국동방항공", "동방항공"], "kind": "foreign"},
    {"id": "chinasouthern", "name": "중국남방항공", "aliases": ["중국남방항공", "남방항공"], "kind": "foreign"},
    {"id": "airchina", "name": "중국국제항공", "aliases": ["중국국제항공", "에어차이나"], "kind": "foreign"},
    {"id": "miat", "name": "몽골항공", "aliases": ["몽골항공", "미아트"], "kind": "foreign"},
    # 동남아
    {"id": "vietjet", "name": "비엣젯항공", "aliases": ["비엣젯항공", "비엣젯"], "kind": "foreign"},
    {"id": "vietnamairlines", "name": "베트남항공", "aliases": ["베트남항공"], "kind": "foreign"},
    {"id": "airasia", "name": "에어아시아", "aliases": ["에어아시아엑스", "타이에어아시아", "에어아시아"], "kind": "foreign"},
    {"id": "cebu", "name": "세부퍼시픽", "aliases": ["세부퍼시픽"], "kind": "foreign"},
    {"id": "pal", "name": "필리핀항공", "aliases": ["필리핀항공"], "kind": "foreign"},
    {"id": "scoot", "name": "스쿠트항공", "aliases": ["스쿠트항공", "스쿠트"], "kind": "foreign"},
    {"id": "sia", "name": "싱가포르항공", "aliases": ["싱가포르항공"], "kind": "foreign"},
    {"id": "thai", "name": "타이항공", "aliases": ["타이항공", "타이국제항공"], "kind": "foreign"},
    {"id": "malaysia", "name": "말레이시아항공", "aliases": ["말레이시아항공"], "kind": "foreign"},
    {"id": "garuda", "name": "가루다인도네시아", "aliases": ["가루다인도네시아", "가루다항공"], "kind": "foreign"},
    {"id": "jetstar", "name": "젯스타", "aliases": ["젯스타"], "kind": "foreign"},
    # 중동·중앙아시아
    {"id": "emirates", "name": "에미레이트항공", "aliases": ["에미레이트항공", "에미레이트"], "kind": "foreign"},
    {"id": "qatar", "name": "카타르항공", "aliases": ["카타르항공"], "kind": "foreign"},
    {"id": "etihad", "name": "에티하드항공", "aliases": ["에티하드항공", "에티하드"], "kind": "foreign"},
    {"id": "turkish", "name": "터키항공", "aliases": ["터키항공", "튀르키예항공"], "kind": "foreign"},
    {"id": "uzbekistan", "name": "우즈베키스탄항공", "aliases": ["우즈베키스탄항공"], "kind": "foreign"},
    # 유럽
    {"id": "finnair", "name": "핀에어", "aliases": ["핀에어"], "kind": "foreign"},
    {"id": "lufthansa", "name": "루프트한자", "aliases": ["루프트한자"], "kind": "foreign"},
    {"id": "airfrance", "name": "에어프랑스", "aliases": ["에어프랑스"], "kind": "foreign"},
    {"id": "klm", "name": "KLM", "aliases": ["KLM", "KLM네덜란드항공"], "kind": "foreign"},
    {"id": "ba", "name": "영국항공", "aliases": ["영국항공", "브리티시항공"], "kind": "foreign"},
    {"id": "lot", "name": "LOT폴란드항공", "aliases": ["LOT폴란드항공", "폴란드항공"], "kind": "foreign"},
    # 미주·대양주
    {"id": "delta", "name": "델타항공", "aliases": ["델타항공"], "kind": "foreign"},
    {"id": "united", "name": "유나이티드항공", "aliases": ["유나이티드항공"], "kind": "foreign"},
    {"id": "american", "name": "아메리칸항공", "aliases": ["아메리칸항공"], "kind": "foreign"},
    {"id": "aircanada", "name": "에어캐나다", "aliases": ["에어캐나다"], "kind": "foreign"},
    {"id": "hawaiian", "name": "하와이안항공", "aliases": ["하와이안항공"], "kind": "foreign"},
    {"id": "qantas", "name": "콴타스항공", "aliases": ["콴타스항공", "콴타스"], "kind": "foreign"},
    {"id": "airnz", "name": "에어뉴질랜드", "aliases": ["에어뉴질랜드"], "kind": "foreign"},
]

BY_ID = {a["id"]: a for a in AIRLINES}
