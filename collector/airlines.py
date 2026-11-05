"""수집 대상 항공사 목록.

name    화면에 표시할 이름이자 뉴스 검색어
aliases 기사 제목에서 이 항공사를 알아보는 표기 (name 포함, 긴 것부터 매칭)
search  뉴스 검색어를 name 대신 여러 개로 쓸 때 (선택). []이면 검색하지 않고 기사·메일·시간표에서 알아보기만 한다.
        항공사마다 수집 때 구글 뉴스 검색이 한 번씩 늘어, 한국어 특가 기사가 드문 곳은 []로 둔다 (2026-11-05).
official_url  화면의 "공식 페이지" 링크. 2026-10-15에 봇임을 밝힌 요청으로 확인했다.
              200·202·403·429·444 응답(서버가 있음)이면 그 주소를 쓰고, 응답 없이 연결이 끊긴 곳
              (피치·에티하드·터키·에어프랑스·KLM·영국항공·유나이티드)과 404였던 싱가포르항공은
              TLS 인증서로 공식 도메인만 확인해 첫 화면 주소를 넣었다.
              이벤트 목록 주소를 확인한 곳(아시아나·이스타)은 이벤트 목록.
              2026-11-05 더한 곳(인천 출발 시간표에 있는데 목록에 없던 항공사)도 같은 방식으로 확인했다.
              인증서 확인이 이 PC에서 막힌 곳(홍콩익스프레스·버진애틀랜틱·로열브루나이)과 응답이 늦거나 끊긴 곳
              (산동·선전항공·에어인디아)은 잘 알려진 공식 도메인 첫 화면을 넣었다.
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
    {"id": "hkexpress", "name": "홍콩익스프레스", "aliases": ["홍콩익스프레스", "HK익스프레스"], "official_url": "https://www.hkexpress.com/ko-kr/", "iata": ["UO"], "kind": "foreign"},
    {"id": "airmacau", "name": "에어마카오", "aliases": ["에어마카오", "마카오항공"], "official_url": "https://www.airmacau.com.mo/", "iata": ["NX"], "kind": "foreign"},
    {"id": "shandong", "name": "산동항공", "aliases": ["산동항공"], "search": [], "official_url": "https://www.sda.cn/", "iata": ["SC"], "kind": "foreign"},
    {"id": "tianjin", "name": "천진항공", "aliases": ["천진항공", "톈진항공"], "search": [], "official_url": "https://www.tianjin-air.com/", "iata": ["GS"], "kind": "foreign"},
    {"id": "hainan", "name": "하이난항공", "aliases": ["하이난항공", "해남항공"], "search": [], "official_url": "https://www.hainanairlines.com/", "iata": ["HU"], "kind": "foreign"},
    {"id": "xiamen", "name": "샤먼항공", "aliases": ["샤먼항공", "하문항공"], "search": [], "official_url": "https://www.xiamenair.com/ko-kr/", "iata": ["MF"], "kind": "foreign"},
    {"id": "shenzhen", "name": "선전항공", "aliases": ["선전항공", "심천항공"], "search": [], "official_url": "https://www.shenzhenair.com/", "iata": ["ZH"], "kind": "foreign"},
    {"id": "sichuan", "name": "쓰촨항공", "aliases": ["쓰촨항공", "사천항공"], "search": [], "official_url": "https://www.sichuanair.com/", "iata": ["3U"], "kind": "foreign"},
    {"id": "spring", "name": "춘추항공", "aliases": ["춘추항공"], "search": [], "official_url": "https://www.ch.com/", "iata": ["9C"], "kind": "foreign"},
    {"id": "aeromongolia", "name": "에어로몽골리아", "aliases": ["에어로몽골리아"], "search": [], "official_url": "https://www.aeromongolia.com/", "iata": ["M0"], "kind": "foreign"},
    # 동남아
    {"id": "vietjet", "name": "비엣젯항공", "aliases": ["비엣젯항공", "비엣젯"], "official_url": "https://www.vietjetair.com/ko", "iata": ["VJ", "VZ"], "kind": "foreign"},
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
    {"id": "sunphuquoc", "name": "썬푸꾸옥항공", "aliases": ["썬푸꾸옥항공", "선푸꾸옥항공", "썬푸꾸옥에어웨이즈"], "official_url": "https://www.sunphuquocairways.com/kr/ko", "iata": ["9G"], "kind": "foreign"},
    {"id": "batik", "name": "바틱에어", "aliases": ["바틱에어"], "official_url": "https://www.batikair.com/", "iata": ["OD"], "kind": "foreign"},
    {"id": "skyangkor", "name": "스카이앙코르항공", "aliases": ["스카이앙코르항공", "스카이앙코르"], "search": [], "official_url": "https://www.skyangkorair.com/", "iata": ["ZA"], "kind": "foreign"},
    {"id": "royalbrunei", "name": "로열브루나이항공", "aliases": ["로열브루나이항공", "로얄브루나이항공"], "search": [], "official_url": "https://www.flyroyalbrunei.com/", "iata": ["BI"], "kind": "foreign"},
    {"id": "mai", "name": "미얀마국제항공", "aliases": ["미얀마국제항공"], "search": [], "official_url": "https://www.maiair.com/", "iata": ["8M"], "kind": "foreign"},
    {"id": "lao", "name": "라오항공", "aliases": ["라오항공"], "search": [], "official_url": "https://www.laoairlines.com/", "iata": ["QV"], "kind": "foreign"},
    {"id": "srilankan", "name": "스리랑카항공", "aliases": ["스리랑카항공"], "search": [], "official_url": "https://www.srilankan.com/", "iata": ["UL"], "kind": "foreign"},
    {"id": "airindia", "name": "에어인디아", "aliases": ["에어인디아"], "search": [], "official_url": "https://www.airindia.com/", "iata": ["AI"], "kind": "foreign"},
    # 중동·중앙아시아
    {"id": "emirates", "name": "에미레이트항공", "aliases": ["에미레이트항공", "에미레이트"], "official_url": "https://www.emirates.com/kr/korean/", "iata": ["EK"], "kind": "foreign"},
    {"id": "qatar", "name": "카타르항공", "aliases": ["카타르항공"], "official_url": "https://www.qatarairways.com/ko-kr/homepage.html", "iata": ["QR"], "kind": "foreign"},
    {"id": "etihad", "name": "에티하드항공", "aliases": ["에티하드항공", "에티하드"], "official_url": "https://www.etihad.com/", "iata": ["EY"], "kind": "foreign"},
    {"id": "turkish", "name": "터키항공", "aliases": ["터키항공", "튀르키예항공"], "official_url": "https://www.turkishairlines.com/", "iata": ["TK"], "kind": "foreign"},
    {"id": "uzbekistan", "name": "우즈베키스탄항공", "aliases": ["우즈베키스탄항공"], "official_url": "https://www.uzairways.com/", "iata": ["HY"], "kind": "foreign"},
    {"id": "airastana", "name": "에어아스타나", "aliases": ["에어아스타나"], "search": [], "official_url": "https://airastana.com/", "iata": ["KC"], "kind": "foreign"},
    {"id": "ethiopian", "name": "에티오피아항공", "aliases": ["에티오피아항공"], "search": [], "official_url": "https://www.ethiopianairlines.com/", "iata": ["ET"], "kind": "foreign"},
    # 유럽
    {"id": "finnair", "name": "핀에어", "aliases": ["핀에어"], "official_url": "https://www.finnair.com/kr-ko", "iata": ["AY"], "kind": "foreign"},
    {"id": "lufthansa", "name": "루프트한자", "aliases": ["루프트한자"], "official_url": "https://www.lufthansa.com/kr/ko/homepage", "iata": ["LH"], "kind": "foreign"},
    {"id": "airfrance", "name": "에어프랑스", "aliases": ["에어프랑스"], "official_url": "https://www.airfrance.co.kr/", "iata": ["AF"], "kind": "foreign"},
    {"id": "klm", "name": "KLM", "aliases": ["KLM", "KLM네덜란드항공"], "official_url": "https://www.klm.com/", "iata": ["KL"], "kind": "foreign"},
    {"id": "ba", "name": "영국항공", "aliases": ["영국항공", "브리티시항공"], "official_url": "https://www.britishairways.com/", "iata": ["BA"], "kind": "foreign"},
    {"id": "lot", "name": "LOT폴란드항공", "aliases": ["LOT폴란드항공", "폴란드항공"], "official_url": "https://www.lot.com/kr/ko", "iata": ["LO"], "kind": "foreign"},
    {"id": "sas", "name": "스칸디나비아항공", "aliases": ["스칸디나비아항공", "SAS항공"], "official_url": "https://www.flysas.com/", "iata": ["SK"], "kind": "foreign"},
    {"id": "virgin", "name": "버진애틀랜틱", "aliases": ["버진애틀랜틱", "버진 애틀랜틱"], "search": [], "official_url": "https://www.virginatlantic.com/", "iata": ["VS"], "kind": "foreign"},
    # 미주·대양주
    {"id": "delta", "name": "델타항공", "aliases": ["델타항공"], "official_url": "https://www.delta.com/", "iata": ["DL"], "kind": "foreign"},
    {"id": "united", "name": "유나이티드항공", "aliases": ["유나이티드항공"], "official_url": "https://www.united.com/", "iata": ["UA"], "kind": "foreign"},
    {"id": "american", "name": "아메리칸항공", "aliases": ["아메리칸항공"], "official_url": "https://www.aa.com/", "iata": ["AA"], "kind": "foreign"},
    {"id": "aircanada", "name": "에어캐나다", "aliases": ["에어캐나다"], "official_url": "https://www.aircanada.com/kr/ko/aco/home.html", "iata": ["AC"], "kind": "foreign"},
    {"id": "alaska", "name": "알래스카항공", "aliases": ["알래스카항공"], "official_url": "https://www.alaskaair.com/", "iata": ["AS"], "kind": "foreign"},
    {"id": "westjet", "name": "웨스트젯", "aliases": ["웨스트젯"], "search": [], "official_url": "https://www.westjet.com/", "iata": ["WS"], "kind": "foreign"},
    {"id": "aeromexico", "name": "아에로멕시코", "aliases": ["아에로멕시코"], "search": [], "official_url": "https://aeromexico.com/", "iata": ["AM"], "kind": "foreign"},
    {"id": "aerolineas", "name": "아르헨티나항공", "aliases": ["아르헨티나항공", "아에롤리네아스 아르헨티나스"], "search": [], "official_url": "https://www.aerolineas.com.ar/", "iata": ["AR"], "kind": "foreign"},
    {"id": "hawaiian", "name": "하와이안항공", "aliases": ["하와이안항공"], "official_url": "https://www.hawaiianairlines.co.kr/", "iata": ["HA"], "kind": "foreign"},
    {"id": "qantas", "name": "콴타스항공", "aliases": ["콴타스항공", "콴타스"], "official_url": "https://www.qantas.com/kr/en.html", "iata": ["QF"], "kind": "foreign"},
    {"id": "airnz", "name": "에어뉴질랜드", "aliases": ["에어뉴질랜드"], "official_url": "https://www.airnewzealand.co.kr/", "iata": ["NZ"], "kind": "foreign"},
]

BY_ID = {a["id"]: a for a in AIRLINES}
