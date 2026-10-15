"""수집 대상 항공사 목록.

name    화면에 표시할 이름이자 뉴스 검색어
aliases 기사 제목에서 이 항공사를 알아보는 표기 (name 포함, 긴 것부터 매칭)
search  뉴스 검색어를 name 대신 여러 개로 쓸 때 (선택)
official_url  화면의 "공식 페이지" 링크. 2026-10-15에 봇임을 밝힌 요청으로 확인했다.
              200·202·403·429·444 응답(서버가 있음)이면 그 주소를 쓰고, 응답 없이 연결이 끊긴 곳
              (피치·에티하드·터키·에어프랑스·KLM·영국항공·유나이티드)과 404였던 싱가포르항공은
              TLS 인증서로 공식 도메인만 확인해 첫 화면 주소를 넣었다.
              이벤트 목록 주소를 확인한 곳(아시아나·이스타)은 이벤트 목록.
kind    domestic | foreign
iata    편명 앞 두 자리(IATA 항공사 코드). 시간표의 편명과 행사 항공사를 이름 대신 이 코드로 맞춘다.
        자회사 여럿이 한 이름으로 묶인 곳(에어아시아·젯스타)은 코드도 여럿이다.
"""

AIRLINES = [
    # 국내 FSC
    {"id": "koreanair", "name": "대한항공", "aliases": ["대한항공"], "official_url": "https://www.koreanair.com/", "iata": ["KE"], "kind": "domestic"},
    {"id": "asiana", "name": "아시아나항공", "aliases": ["아시아나항공", "아시아나"], "official_url": "https://flyasiana.com/C/KR/KO/event/list", "iata": ["OZ"], "kind": "domestic"},
    # 국내 LCC
    {"id": "jejuair", "name": "제주항공", "aliases": ["제주항공"], "official_url": "https://www.jejuair.net/", "iata": ["7C"], "kind": "domestic"},
    {"id": "jinair", "name": "진에어", "aliases": ["진에어"], "official_url": "https://www.jinair.com/", "iata": ["LJ"], "kind": "domestic"},
    # 2026-09-10 티웨이항공 → 트리니티항공 사명 변경. 옛 이름 기사도 같은 항공사로 본다.
    {"id": "trinity", "name": "트리니티항공", "aliases": ["트리니티항공", "트리니티", "티웨이항공", "티웨이"],
     "search": ["트리니티항공", "티웨이항공"], "official_url": "https://www.twayair.com/", "iata": ["TW"], "kind": "domestic"},
    {"id": "airbusan", "name": "에어부산", "aliases": ["에어부산"], "official_url": "https://www.airbusan.com/", "iata": ["BX"], "kind": "domestic"},
    {"id": "airseoul", "name": "에어서울", "aliases": ["에어서울"], "official_url": "https://flyairseoul.com/", "iata": ["RS"], "kind": "domestic"},
    {"id": "eastarjet", "name": "이스타항공", "aliases": ["이스타항공", "이스타"], "official_url": "https://www.eastarjet.com/newstar/PGWTA00001", "iata": ["ZE"], "kind": "domestic"},
    {"id": "airpremia", "name": "에어프레미아", "aliases": ["에어프레미아"], "official_url": "https://www.airpremia.com/", "iata": ["YP"], "kind": "domestic"},
    {"id": "aerok", "name": "에어로케이", "aliases": ["에어로케이"], "official_url": "https://www.aerok.com/", "iata": ["RF"], "kind": "domestic"},
    {"id": "parataair", "name": "파라타항공", "aliases": ["파라타항공", "파라타"], "official_url": "https://www.parataair.com/", "iata": ["WE"], "kind": "domestic"},
    # 일본
    {"id": "jal", "name": "일본항공", "aliases": ["일본항공", "JAL"], "official_url": "https://www.jal.co.jp/kr/ko/", "iata": ["JL"], "kind": "foreign"},
    {"id": "ana", "name": "전일본공수", "aliases": ["전일본공수", "ANA"], "official_url": "https://www.ana.co.jp/ko/kr/", "iata": ["NH"], "kind": "foreign"},
    {"id": "peach", "name": "피치항공", "aliases": ["피치항공", "피치애비에이션"], "official_url": "https://www.flypeach.com/", "iata": ["MM"], "kind": "foreign"},
    {"id": "zipair", "name": "집에어", "aliases": ["집에어", "ZIPAIR"], "official_url": "https://www.zipair.net/ko", "iata": ["ZG"], "kind": "foreign"},
    # 중화권·몽골
    {"id": "cathay", "name": "캐세이퍼시픽", "aliases": ["캐세이퍼시픽"], "official_url": "https://www.cathaypacific.com/cx/ko_KR.html", "iata": ["CX"], "kind": "foreign"},
    {"id": "hkair", "name": "홍콩항공", "aliases": ["홍콩항공"], "official_url": "https://www.hongkongairlines.com/", "iata": ["HX"], "kind": "foreign"},
    {"id": "eva", "name": "에바항공", "aliases": ["에바항공"], "official_url": "https://www.evaair.com/ko-kr/index.html", "iata": ["BR"], "kind": "foreign"},
    {"id": "chinaairlines", "name": "중화항공", "aliases": ["중화항공"], "official_url": "https://www.china-airlines.com/kr/ko", "iata": ["CI"], "kind": "foreign"},
    {"id": "starlux", "name": "스타럭스항공", "aliases": ["스타럭스항공", "스타럭스"], "official_url": "https://www.starlux-airlines.com/ko-KR", "iata": ["JX"], "kind": "foreign"},
    {"id": "tigertw", "name": "타이거에어", "aliases": ["타이거에어"], "official_url": "https://www.tigerairtw.com/ko-kr", "iata": ["IT"], "kind": "foreign"},
    {"id": "chinaeastern", "name": "중국동방항공", "aliases": ["중국동방항공", "동방항공"], "official_url": "https://kr.ceair.com/", "iata": ["MU"], "kind": "foreign"},
    {"id": "chinasouthern", "name": "중국남방항공", "aliases": ["중국남방항공", "남방항공"], "official_url": "https://www.csair.com/kr/ko/", "iata": ["CZ"], "kind": "foreign"},
    {"id": "airchina", "name": "중국국제항공", "aliases": ["중국국제항공", "에어차이나"], "official_url": "https://www.airchina.kr/", "iata": ["CA"], "kind": "foreign"},
    {"id": "miat", "name": "몽골항공", "aliases": ["몽골항공", "미아트"], "official_url": "https://www.miat.com/", "iata": ["OM"], "kind": "foreign"},
    # 동남아
    {"id": "vietjet", "name": "비엣젯항공", "aliases": ["비엣젯항공", "비엣젯"], "official_url": "https://www.vietjetair.com/ko", "iata": ["VJ"], "kind": "foreign"},
    {"id": "vietnamairlines", "name": "베트남항공", "aliases": ["베트남항공"], "official_url": "https://www.vietnamairlines.com/kr/ko/home", "iata": ["VN"], "kind": "foreign"},
    {"id": "airasia", "name": "에어아시아", "aliases": ["에어아시아엑스", "타이에어아시아", "에어아시아"], "official_url": "https://www.airasia.com/ko/kr", "iata": ["AK", "D7", "FD", "Z2", "XJ"], "kind": "foreign"},
    {"id": "cebu", "name": "세부퍼시픽", "aliases": ["세부퍼시픽"], "official_url": "https://www.cebupacificair.com/ko-KR", "iata": ["5J"], "kind": "foreign"},
    {"id": "pal", "name": "필리핀항공", "aliases": ["필리핀항공"], "official_url": "https://www.philippineairlines.com/", "iata": ["PR"], "kind": "foreign"},
    {"id": "scoot", "name": "스쿠트항공", "aliases": ["스쿠트항공", "스쿠트"], "official_url": "https://www.flyscoot.com/ko", "iata": ["TR"], "kind": "foreign"},
    {"id": "sia", "name": "싱가포르항공", "aliases": ["싱가포르항공"], "official_url": "https://www.singaporeair.com/", "iata": ["SQ"], "kind": "foreign"},
    {"id": "thai", "name": "타이항공", "aliases": ["타이항공", "타이국제항공"], "official_url": "https://www.thaiairways.com/ko-kr/", "iata": ["TG"], "kind": "foreign"},
    {"id": "malaysia", "name": "말레이시아항공", "aliases": ["말레이시아항공"], "official_url": "https://www.malaysiaairlines.com/kr/ko.html", "iata": ["MH"], "kind": "foreign"},
    {"id": "garuda", "name": "가루다인도네시아", "aliases": ["가루다인도네시아", "가루다항공"], "official_url": "https://www.garuda-indonesia.com/", "iata": ["GA"], "kind": "foreign"},
    {"id": "jetstar", "name": "젯스타", "aliases": ["젯스타"], "official_url": "https://www.jetstar.com/kr/ko/home", "iata": ["JQ", "3K", "GK"], "kind": "foreign"},
    # 중동·중앙아시아
    {"id": "emirates", "name": "에미레이트항공", "aliases": ["에미레이트항공", "에미레이트"], "official_url": "https://www.emirates.com/kr/korean/", "iata": ["EK"], "kind": "foreign"},
    {"id": "qatar", "name": "카타르항공", "aliases": ["카타르항공"], "official_url": "https://www.qatarairways.com/ko-kr/homepage.html", "iata": ["QR"], "kind": "foreign"},
    {"id": "etihad", "name": "에티하드항공", "aliases": ["에티하드항공", "에티하드"], "official_url": "https://www.etihad.com/", "iata": ["EY"], "kind": "foreign"},
    {"id": "turkish", "name": "터키항공", "aliases": ["터키항공", "튀르키예항공"], "official_url": "https://www.turkishairlines.com/", "iata": ["TK"], "kind": "foreign"},
    {"id": "uzbekistan", "name": "우즈베키스탄항공", "aliases": ["우즈베키스탄항공"], "official_url": "https://www.uzairways.com/", "iata": ["HY"], "kind": "foreign"},
    # 유럽
    {"id": "finnair", "name": "핀에어", "aliases": ["핀에어"], "official_url": "https://www.finnair.com/kr-ko", "iata": ["AY"], "kind": "foreign"},
    {"id": "lufthansa", "name": "루프트한자", "aliases": ["루프트한자"], "official_url": "https://www.lufthansa.com/kr/ko/homepage", "iata": ["LH"], "kind": "foreign"},
    {"id": "airfrance", "name": "에어프랑스", "aliases": ["에어프랑스"], "official_url": "https://www.airfrance.co.kr/", "iata": ["AF"], "kind": "foreign"},
    {"id": "klm", "name": "KLM", "aliases": ["KLM", "KLM네덜란드항공"], "official_url": "https://www.klm.com/", "iata": ["KL"], "kind": "foreign"},
    {"id": "ba", "name": "영국항공", "aliases": ["영국항공", "브리티시항공"], "official_url": "https://www.britishairways.com/", "iata": ["BA"], "kind": "foreign"},
    {"id": "lot", "name": "LOT폴란드항공", "aliases": ["LOT폴란드항공", "폴란드항공"], "official_url": "https://www.lot.com/kr/ko", "iata": ["LO"], "kind": "foreign"},
    # 미주·대양주
    {"id": "delta", "name": "델타항공", "aliases": ["델타항공"], "official_url": "https://www.delta.com/", "iata": ["DL"], "kind": "foreign"},
    {"id": "united", "name": "유나이티드항공", "aliases": ["유나이티드항공"], "official_url": "https://www.united.com/", "iata": ["UA"], "kind": "foreign"},
    {"id": "american", "name": "아메리칸항공", "aliases": ["아메리칸항공"], "official_url": "https://www.aa.com/", "iata": ["AA"], "kind": "foreign"},
    {"id": "aircanada", "name": "에어캐나다", "aliases": ["에어캐나다"], "official_url": "https://www.aircanada.com/kr/ko/aco/home.html", "iata": ["AC"], "kind": "foreign"},
    {"id": "hawaiian", "name": "하와이안항공", "aliases": ["하와이안항공"], "official_url": "https://www.hawaiianairlines.co.kr/", "iata": ["HA"], "kind": "foreign"},
    {"id": "qantas", "name": "콴타스항공", "aliases": ["콴타스항공", "콴타스"], "official_url": "https://www.qantas.com/kr/en.html", "iata": ["QF"], "kind": "foreign"},
    {"id": "airnz", "name": "에어뉴질랜드", "aliases": ["에어뉴질랜드"], "official_url": "https://www.airnewzealand.co.kr/", "iata": ["NZ"], "kind": "foreign"},
]

BY_ID = {a["id"]: a for a in AIRLINES}
