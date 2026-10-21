// 상태 규칙은 collector/status.py와 같다. 페이지를 연 날(KST) 기준으로 다시 계산한다.
(function () {
  "use strict";

  var DAY = 86400000;
  var WEEK = ["일", "월", "화", "수", "목", "금", "토"];
  var STATUS_LABEL = { upcoming: "판매 예정", live: "진행 중", undated: "날짜 미확인", stale: "진행 여부 미확인", ended: "마감" };
  var STATUS_PILL = { upcoming: "", live: "green", undated: "orange", stale: "gray", ended: "gray" };
  var CLOSING_DAYS = 3; // 마감까지 이 일수 이내면 '마감 임박'
  var ORDER = { upcoming: 0, live: 1, undated: 2, stale: 3, ended: 4 };
  // 마감일을 모르는 행사는 마지막 기사 후 이 일수가 지나면 '진행 여부 미확인'으로 목록 아래에 접는다 (collector/status.py)
  var STALE_AFTER_DAYS = 14;
  var ICN_LABEL = { yes: "인천(ICN)", no: "인천 외 출발", unknown: "미확인" };
  var VERIFY_LABEL = { official: "공식 확인", news: "뉴스 기반 · 미확인" };
  var NEW_HOURS = 48;   // 처음 본 지 이 시간 안이면 '신규', 기사가 이 시간 안에 더해졌으면 '기사 추가'
  var STALE_HOURS = 12; // 마지막 수집이 이보다 오래되면 수집이 멈춘 것으로 본다

  // 행사 종류 탭. kinds는 '구분' 선택지(빈 배열이면 숨김), who는 항공사/브랜드 라벨
  var SECTIONS = {
    flight: { kinds: [["all", "전체 항공사"], ["domestic", "국내 항공사"], ["foreign", "해외 항공사"]], who: "항공사",
              placeholder: "일본, 얼리버드, 하와이…",
              empty: "조건에 맞는 행사가 없습니다. 필터를 바꿔 보세요." },
    domestic: { kinds: [], who: "항공사", placeholder: "제주, 김포, 추석…",
                empty: "지금은 국내선 행사가 없습니다. 제목에 '국내선'·'김포~제주' 같은 노선 표현이 있는 기사만 국내선으로 분류합니다." },
    hotel: { kinds: [["all", "전체"], ["hotel", "호텔·리조트"], ["platform", "예약 플랫폼·여행사"], ["campaign", "정부 할인 행사"], ["other", "브랜드 미확인"]], who: "브랜드",
             placeholder: "제주, 페스타, 호캉스…",
             empty: "조건에 맞는 숙박 행사가 없습니다. 필터를 바꿔 보세요." }
  };

  var FILTER_LABEL = { live: "진행 중", "new": "신규", closing: "마감 임박", upcoming: "판매 예정", official: "공식 확인", undated: "날짜 미확인", ended: "마감" };

  var state = { section: "flight", filter: "all", kind: "all", airline: "all", q: "", hideOther: true, scope: "all", sort: "default" };
  var deals = [];
  var names = {};       // airline_id -> 이름 (필터용)
  var baselines = {};   // 묶음별 첫 수집 시각. 이때 들어온 기사는 신규로 보지 않는다

  function todayKst() {
    return new Date(Date.now() + 9 * 3600000).toISOString().slice(0, 10);
  }
  function diffDays(a, b) { // a - b (일)
    return Math.round((Date.parse(a) - Date.parse(b)) / DAY);
  }
  function md(iso) {
    var d = new Date(iso + "T00:00:00Z");
    // 올해가 아닌 날짜는 연도를 붙인다 (예: 내년 1분기 탑승)
    var y = d.getUTCFullYear() === Number(todayKst().slice(0, 4)) ? "" : d.getUTCFullYear() + "/";
    return y + (d.getUTCMonth() + 1) + "/" + d.getUTCDate() + "(" + WEEK[d.getUTCDay()] + ")";
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function statusOf(d, today) {
    if (d.sale_start && today < d.sale_start) return "upcoming";
    if (d.sale_end && today > d.sale_end) return "ended";
    if (!d.sale_end && diffDays(today, d.last_published) > STALE_AFTER_DAYS) return "stale";
    if (d.sale_start || d.sale_end) return "live";
    return "undated";
  }

  function ddayText(d, st, today) {
    if (st === "upcoming") return "D-" + diffDays(d.sale_start, today);
    if (st === "live") {
      if (d.sale_end) {
        var left = diffDays(d.sale_end, today);
        return left === 0 ? "오늘 마감" : "마감 D-" + left;
      }
      return diffDays(today, d.sale_start) + 1 + "일째";
    }
    if (st === "ended") return diffDays(today, d.sale_end) + "일 전 마감";
    return "기사 " + md(d.last_published);
  }

  function sectionOf(d) { return d.section || "flight"; } // section이 없던 예전 데이터는 항공권

  function freshness(d) {
    var now = Date.now(), win = NEW_HOURS * 3600000, baseline = baselines[d.baseline || sectionOf(d)] || baselines[sectionOf(d)] || "";
    if (d.first_seen && d.first_seen > baseline && now - Date.parse(d.first_seen) <= win) return "new";
    if (d.last_seen && d.last_seen > baseline && now - Date.parse(d.last_seen) <= win) return "updated";
    return null;
  }

  // 기사에 없는 쪽 날짜는 만들지 않고 '미확인'으로 둔다. 둘 다 없으면 null
  function rangeText(start, end) {
    if (!start && !end) return null;
    return (start ? md(start) : "미확인") + " ~ " + (end ? md(end) : "미확인");
  }

  function isClosing(d, today) {
    return d._status === "live" && d.sale_end && diffDays(d.sale_end, today) <= CLOSING_DAYS;
  }

  function matches(d, f, today) {
    if (d._status === "stale") return f === "stale"; // 접힌 칸에만 보인다 ('전체'·'신규' 수에도 넣지 않는다)
    if (f === "all") return true;
    if (f === "new") return d._fresh === "new";
    if (f === "closing") return isClosing(d, today);
    if (f === "official") return d.verification === "official";
    return d._status === f;
  }

  function row(label, value, cls, ev) {
    return "<dt>" + label + "</dt><dd" + (cls ? ' class="' + cls + '"' : "") + ">" + value + (ev || "") + "</dd>";
  }

  // 값을 뽑아 온 기사 링크. 기사 제목을 툴팁으로 보여준다
  function evLink(d, field) {
    var e = (d.evidence || {})[field];
    return e ? ' <a class="ev" href="' + esc(e.url) + '" target="_blank" rel="noopener" title="근거 기사: ' + esc(e.title) + '">근거</a>' : "";
  }

  // 호텔 지역: '해외 · 괌', '국내 · 강원 · 경남'. 지명이 없으면 국내/해외만 또는 미확인
  function regionText(d) {
    var scope = d.scope === "overseas" ? "해외" : d.scope === "domestic" ? "국내" : "";
    var names = (d.regions || []).join(" · ");
    return esc([scope, names].filter(Boolean).join(" · ")) || "미확인";
  }

  // 공식 링크 이름. 대부분 홈페이지 첫 화면이라 행사 페이지처럼 부르지 않는다.
  // 이벤트 목록 주소를 확인한 곳(아시아나 /event/list, 이스타 PGWTA00001 — collector/airlines.py)만 '이벤트 목록'
  var EVENT_LIST_URL = /\/event\/|PGWTA00001/i;
  function officialLabel(d) {
    if (EVENT_LIST_URL.test(d.official_url)) return "공식 이벤트 목록";
    return sectionOf(d) === "hotel" ? "공식 홈페이지" : "항공사 홈페이지";
  }
  function officialLink(d, cls) {
    return d.official_url ? '<a' + (cls ? ' class="' + cls + '"' : "") + ' href="' + esc(d.official_url) +
      '" target="_blank" rel="noopener" title="행사 안내 페이지가 아닐 수 있습니다">' + officialLabel(d) + " ↗</a>" : "";
  }

  function routesText(d) {
    return (d.routes || []).map(function (r) {
      return esc(r.origin || "출발 미확인") + " → " + esc(r.destination || "도착 미확인");
    }).join(", ");
  }

  // ---------------------------------------------------------------- 행사 항공사의 인천 출발 운항 도착지
  // 좌석이 남았는지·할인가는 알 수 없다. 인천공항 정기 일정으로 '어디로 운항하는지'만 보여준다.
  var destCache = {};

  function airlineDestinations(codes) {
    var key = codes.join(",");
    if (destCache[key]) return destCache[key];
    var today = todayKst(), end = sch.coverage.full_until, by = {};
    var days = [];
    for (var i = 0; i < 7; i++) {
      var iso = new Date(Date.parse(today) + i * DAY).toISOString().slice(0, 10);
      if (iso <= end) days.push(iso);
    }
    sch.schedule.forEach(function (r) {
      if (r.codeshare_of || codes.indexOf(prefixOf(r.flight)) < 0 || r.last < today) return;
      var g = by[r.dest_code] || (by[r.dest_code] = { code: r.dest_code, name: r.dest, week: 0, last: r.last });
      if (r.last > g.last) g.last = r.last;
      days.forEach(function (iso) {
        if (r.first <= iso && iso <= r.last && r.days.charAt(weekdayIdx(iso)) === "1") g.week++;
      });
    });
    var list = Object.keys(by).map(function (k) { return by[k]; }).filter(function (g) { return g.week > 0; })
      .sort(function (a, b) { return b.week - a.week || a.name.localeCompare(b.name, "ko"); });
    return (destCache[key] = { list: list, days: days.length });
  }

  function airlineDestBlock(d) {
    if (sectionOf(d) === "hotel" || !(d.iata || []).length) return "";
    if (!sch) return schError ? "" : '<div class="dest-block muted">인천 출발 운항 도착지: 시간표 불러오는 중…</div>';
    var info = airlineDestinations(d.iata);
    var routes = d.routes || [];
    var target = function (g) {
      return routes.some(function (r) {
        var dest = r.destination || "";
        return r.origin === "인천(ICN)" && (dest.indexOf("(" + g.code + ")") >= 0 || dest === g.name);
      });
    };
    var other = routes.filter(function (r) { return r.origin && r.origin !== "인천(ICN)"; })
      .map(function (r) { return r.origin + " → " + (r.destination || "도착 미확인"); });
    var nTarget = info.list.filter(target).length;
    var head = info.list.length
      ? "인천 출발 운항 도착지 " + info.list.length + "곳 · 앞으로 " + info.days + "일간 " +
        info.list.reduce(function (n, g) { return n + g.week; }, 0) + "편"
      : "인천 출발 정기편 없음 (확보된 시간표 기준)";
    var items = info.list.map(function (g) {
      return "<li" + (target(g) ? ' class="hit"' : "") + ">" + esc(g.name) + ' <span class="cs">' + esc(g.code) + "</span> " +
        g.week + "편" + (g.last < sch.coverage.full_until ? ' <span class="cs">' + md(g.last) + "까지 운항</span>" : "") +
        (target(g) ? ' <span class="pill green">행사 대상 확인</span>' : "") + "</li>";
    }).join("");
    return '<details class="dest-block"><summary>' + head + "</summary>" +
      '<p class="dest-note">행사 대상 노선: ' + (nTarget ? nTarget + "곳 기사로 확인" : "기사에서 인천 출발 노선 확인 안 됨") +
        (other.length ? " · 기사 노선은 " + esc(other.join(", ")) : "") +
        "<br>좌석이 남았는지·할인가는 알 수 없습니다 (" + (d.official_url ? officialLink(d) + "에서 확인" : "공식 페이지에서 확인") + ")." +
        " 편수는 인천공항 정기 일정 기준 공동운항 판매 편명 제외, " + md(sch.coverage.full_until) + "까지 확보.</p>" +
      (items ? "<ul>" + items + "</ul>" : "") + "</details>";
  }

  // 남은 기간 칸: 위에 무엇까지의 기간인지, 아래에 D-day
  function ddayBox(d, st, today) {
    var label = st === "upcoming" ? "판매 시작" : st === "live" ? (d.sale_end ? "판매 마감" : "판매 중") : st === "ended" ? "판매 종료" : "판매 기간";
    var value = st === "undated" ? "미확인" : st === "stale" ? "진행 여부 미확인" : ddayText(d, st, today).replace(/^마감 /, ""); // 위 칸이 '판매 마감'이라 겹치는 말은 뺀다
    var cls = isClosing(d, today) ? " urgent" : st === "ended" || st === "stale" ? " past" : st === "undated" ? " unk" : "";
    return '<div class="dday' + cls + '"><span>' + label + "</span><b>" + esc(value) + "</b></div>";
  }

  // 카드 앞면은 '어디로·얼마나·언제까지'만. 나머지 기간·출발 공항·근거·기사는 '상세 정보'에 접어 둔다
  function card(d, today) {
    var st = d._status;
    var title = d.event_name ? d.event_name : d.headline;
    var multi = d.airline_id === "multi";
    var sec = sectionOf(d), hotel = sec === "hotel";
    var sale = rangeText(d.sale_start, d.sale_end);
    var travel = rangeText(d.travel_start, d.travel_end);
    var verified = d.verification === "official";
    var arts = d.articles.map(function (a) {
      return '<li><a href="' + esc(a.url) + '" target="_blank" rel="noopener">' + esc(a.title) + "</a>" +
        "<span>" + esc(a.outlet || "") + " · " + md(a.published) + "</span></li>";
    }).join("");
    var pills =
      '<span class="pill ' + STATUS_PILL[st] + '">' + STATUS_LABEL[st] + "</span>" +
      (d._fresh === "new" ? '<span class="pill solid">신규</span>' : d._fresh === "updated" ? '<span class="pill">기사 추가</span>' : "") +
      (isClosing(d, today) ? '<span class="pill orange">마감 임박</span>' : "") +
      (verified ? '<span class="pill green">' + VERIFY_LABEL.official + "</span>" : "") +
      (multi ? '<span class="pill orange">' + SECTIONS[sec].who + " 미분류</span>" : "") +
      (d.trial ? '<span class="pill orange">시범</span>' : "") +
      (hotel && d.scope === "overseas" ? '<span class="pill">해외</span>' : "") +
      (d.lang === "en" ? '<span class="pill gray">영문 기사 · 번역 안 함</span>' : "");
    var airline = multi ? esc(d.airline) + " (" + esc(d.airlines_mentioned.join("·")) + ")" : esc(d.airline);
    var routes = routesText(d);
    var where = hotel ? regionText(d) : routes;
    var travelConflict = (d.conflicts || []).indexOf("travel") >= 0;
    var travelLabel = hotel ? "투숙 기간" : "탑승 기간";
    var travelRow = travelConflict
      ? row(travelLabel, "출처 간 불일치 · 관련 기사 확인", "conflict")
      : row(travelLabel, travel || "미확인", travel ? "" : "unk", travel ? evLink(d, "travel") : "");
    var rows = hotel
      ? row("지역", regionText(d), (d.regions || []).length || d.scope ? "" : "unk") +
        row("판매 기간", sale || "미확인", sale ? "" : "unk", sale ? evLink(d, "sale") : "") +
        travelRow +
        row("조건", (d.conditions || []).length ? esc(d.conditions.join(" · ")) : "미확인", (d.conditions || []).length ? "" : "unk")
      : row("노선", routes || (sec === "domestic" ? "국내선 · 구간 미확인" : "미확인"), routes ? "" : "unk", routes ? evLink(d, "route") : "") +
        row("판매 기간", sale || "미확인", sale ? "" : "unk", sale ? evLink(d, "sale") : "") +
        travelRow +
        (sec === "domestic" ? "" : row("출발 공항", ICN_LABEL[d.from_icn], d.from_icn === "yes" ? "icn" : d.from_icn === "unknown" ? "unk" : ""));
    // 앞면 한 줄 요약: 판매 기간, 탑승(투숙) 기간이 확인된 것만
    var brief = [sale ? "판매 " + sale : "", travel && !travelConflict ? travelLabel.slice(0, 2) + " " + travel : ""].filter(Boolean).join(" · ");
    return '<article class="deal' + (st === "ended" || st === "stale" ? " ended" : "") + '">' +
      '<div class="pills">' + pills + "</div>" +
      '<div class="who">' + airline + (where && where !== "미확인" ? '<span class="where">' + where + "</span>" : "") + "</div>" +
      "<h3>" + esc(title) + "</h3>" +
      '<div class="keyline">' +
        (d.discount ? '<div class="price">' + esc(d.discount) + evLink(d, "discount") + "</div>" : '<div class="price none">할인 조건 확인 필요</div>') +
        ddayBox(d, st, today) +
      "</div>" +
      (brief ? '<p class="brief">' + brief + "</p>" : "") +
      '<div class="foot-row main-foot"><span>' + (verified ? "항공사 공식 확인" : "뉴스 기사 기반 · 예약 전 공식 확인") + "</span>" +
        officialLink(d, "official-link") +
      "</div>" +
      '<details class="more"><summary>상세 정보 · 관련 기사 ' + d.articles.length + "건</summary>" +
        "<dl>" + row(SECTIONS[sec].who, airline) + rows +
          (st === "undated" || st === "stale" ? row("최근 기사", md(d.last_published)) : "") + "</dl>" +
        '<div class="foot">' +
          ((d.agencies || []).length ? '<div class="foot-row"><span>기사에 나온 판매처</span><span>' + d.agencies.map(function (g) {
            return '<a href="' + esc(g.url) + '" target="_blank" rel="noopener">' + esc(g.name) + " ↗</a>";
          }).join(" · ") + "</span></div>" : "") +
          airlineDestBlock(d) +
          '<div class="arts"><b>관련 기사</b>' + (d.event_name ? ' <span class="cs">' + esc(d.headline) + "</span>" : "") + "<ul>" + arts + "</ul></div>" +
        "</div>" +
      "</details>" +
    "</article>";
  }

  // 할인율 정렬용: 할인 표기 안의 가장 큰 % (없으면 -1 → 맨 뒤)
  function pctOf(d) {
    var m = String(d.discount || "").match(/\d{1,3}(?=\s*%)/g);
    return m ? Math.max.apply(null, m.map(Number)) : -1;
  }

  // 정렬. 같은 값이면 원래(상태순) 순서를 지킨다
  function sorted(list) {
    if (state.sort === "default") return list;
    var key = {
      recent: function (d) { return [-(Date.parse(d.first_seen || d.last_published) || 0)]; },
      closing: function (d) {
        var open = d._status === "live" || d._status === "upcoming";
        return [open && d.sale_end ? 0 : 1, open && d.sale_end ? Date.parse(d.sale_end) : 0];
      },
      discount: function (d) { return [-pctOf(d)]; }
    }[state.sort];
    return list.map(function (d, i) { return { d: d, k: key(d).concat(i) }; }).sort(function (a, b) {
      for (var j = 0; j < a.k.length; j++) if (a.k[j] !== b.k[j]) return a.k[j] - b.k[j];
      return 0;
    }).map(function (x) { return x.d; });
  }

  // 적용된 조건을 한 줄로 보여주고 초기화할 수 있게 한다
  function activeConditions() {
    var out = [];
    if (state.filter !== "all") out.push(FILTER_LABEL[state.filter]);
    var kind = document.getElementById("kind");
    if (state.kind !== "all" && kind.selectedIndex >= 0) out.push(kind.options[kind.selectedIndex].text);
    var scope = document.getElementById("scope");
    if (state.section === "hotel" && state.scope !== "all") out.push(scope.options[scope.selectedIndex].text);
    if (state.airline !== "all") out.push(names[state.airline] || state.airline);
    if (state.q) out.push("'" + state.q + "'");
    return out;
  }

  function resetFilters() {
    state.filter = "all"; state.kind = "all"; state.airline = "all"; state.q = ""; state.scope = "all";
    ["kind", "airline", "scope"].forEach(function (id) { document.getElementById(id).value = "all"; });
    document.getElementById("q").value = "";
    render();
  }

  function visible(d) {
    if (sectionOf(d) !== state.section) return false;
    if (state.kind !== "all" && d.kind !== state.kind) return false;
    if (state.section === "hotel" && state.scope !== "all" && (d.scope || "unknown") !== state.scope) return false;
    if (state.airline !== "all" && d.airline_id !== state.airline &&
        (d.airlines_mentioned || []).indexOf(names[state.airline]) < 0) return false;
    if (state.section === "flight" && state.hideOther && d.from_icn === "no") return false;
    if (state.q) {
      var hay = (d.airline + " " + (d.event_name || "") + " " + routesText(d) + " " + (d.regions || []).join(" ") + " " + d.articles.map(function (a) { return a.title; }).join(" ")).toLowerCase();
      if (hay.indexOf(state.q.toLowerCase()) < 0) return false;
    }
    return true;
  }

  function render() {
    var today = todayKst();
    updateTabCounts();
    var base = deals.filter(visible);
    renderList(base, today);
    renderSecretFlying();
    writeUrl();
  }

  // ---------------------------------------------------------------- Secret Flying 게시 가격 (서울 출발)
  var sf = null; // secretflying.json. 없거나 실패하면 이 칸을 숨긴다
  var CURRENCY = { USD: "$", EUR: "€", GBP: "£", JPY: "¥", KRW: "₩" };

  function sfPrice(d) {
    var sym = CURRENCY[d.currency];
    var n = Number(d.price).toLocaleString("en-US");
    return sym ? sym + n + (d.currency === "USD" ? " USD" : "") : n + " " + d.currency;
  }

  function renderSecretFlying() {
    var box = document.getElementById("sf");
    var list = sf && sf.deals || [];
    box.hidden = state.section !== "flight" || !list.length;
    if (box.hidden) return;
    document.getElementById("sf-list").innerHTML = list.map(function (d) {
      return '<li><a href="' + esc(d.url) + '" target="_blank" rel="noopener" title="' + esc(d.title) + '">' +
        '<span class="sf-route">서울 → ' + esc(d.destination) + "</span>" +
        '<span class="sf-price">' + esc(sfPrice(d)) + "</span>" +
        '<span class="sf-meta">' + (d.trip === "oneway" ? "편도" : "왕복") + (d.nonstop ? " · 직항" : "") +
          (d.tag ? " · " + esc(d.tag) : "") + " · " + md(d.first_seen) + " 확인 ↗</span></a></li>";
    }).join("");
  }

  // ---------------------------------------------------------------- 주소에 검색·필터 상태 저장
  // #탭?q=…&f=…&kind=…&scope=…&airline=…&sort=…&icn=0 형식. 기본값은 넣지 않는다.
  // 예전 주소(#hotel, #domestic, #flights)도 그대로 열린다. 항공권 탭에 조건이 없으면 해시를 비운다.
  function parseHash() {
    var h = location.hash.slice(1), i = h.indexOf("?");
    var raw = decodeURIComponent(i < 0 ? h : h.slice(0, i));
    return { raw: raw, sec: SECTIONS[raw] || raw === "flights" ? raw : "flight", p: new URLSearchParams(i < 0 ? "" : h.slice(i + 1)) };
  }

  function writeUrl() {
    if (state.section === "flights") return;
    var p = new URLSearchParams();
    if (state.q) p.set("q", state.q);
    if (state.filter !== "all") p.set("f", state.filter);
    if (state.kind !== "all") p.set("kind", state.kind);
    if (state.section === "hotel" && state.scope !== "all") p.set("scope", state.scope);
    if (state.airline !== "all") p.set("airline", state.airline);
    if (state.sort !== "default") p.set("sort", state.sort);
    if (state.section === "flight" && !state.hideOther) p.set("icn", "0");
    var qs = p.toString();
    var url = state.section === "flight" && !qs ? location.pathname + location.search : "#" + state.section + (qs ? "?" + qs : "");
    try { history.replaceState(null, "", url); } catch (e) { /* 미리보기 등 */ }
  }

  // 주소 값을 상태와 입력 칸에 반영한다. 선택지에 없는 값은 무시하고 기본값으로 둔다
  function applyParams(p) {
    function opt(id, v) {
      var sel = document.getElementById(id);
      return v && [].some.call(sel.options, function (o) { return o.value === v; }) ? v : "all";
    }
    state.q = (p.get("q") || "").trim();
    state.filter = FILTER_LABEL[p.get("f")] ? p.get("f") : "all";
    state.kind = opt("kind", p.get("kind"));
    state.scope = state.section === "hotel" ? opt("scope", p.get("scope")) : "all";
    state.airline = opt("airline", p.get("airline"));
    var sort = opt("sort", p.get("sort"));
    state.sort = sort === "all" ? "default" : sort;
    state.hideOther = p.get("icn") !== "0";
    document.getElementById("q").value = state.q;
    document.getElementById("kind").value = state.kind;
    document.getElementById("scope").value = state.scope;
    document.getElementById("airline").value = state.airline;
    document.getElementById("sort").value = state.sort;
    document.getElementById("hide-other").checked = state.hideOther;
  }

  // 탭 숫자는 어느 탭에 있든 행사 데이터 기준으로 채운다 (시간표 탭으로 바로 들어와도)
  function updateTabCounts() {
    Object.keys(SECTIONS).forEach(function (sec) {
      document.getElementById("n-" + sec).textContent = deals.filter(function (d) {
        return sectionOf(d) === sec && d._status !== "stale" && !(sec === "flight" && state.hideOther && d.from_icn === "no");
      }).length;
    });
    document.querySelectorAll("[data-section]").forEach(function (b) {
      b.setAttribute("aria-pressed", String(b.dataset.section === state.section));
    });
  }

  function renderList(base, today) {
    ["all", "live", "new", "upcoming", "official", "undated", "ended", "closing"].forEach(function (f) {
      var n = base.filter(function (d) { return matches(d, f, today); }).length;
      var c = document.getElementById("c-" + f), t = document.getElementById("s-" + f);
      if (c) c.textContent = n;
      if (t) t.textContent = n;
    });
    document.querySelectorAll("[data-filter]").forEach(function (b) {
      var on = b.dataset.filter === state.filter;
      b.classList.toggle("active", on);
      b.setAttribute("aria-pressed", String(on));
    });
    document.getElementById("official-btn").hidden = !base.some(function (d) { return d.verification === "official"; });
    var shown = sorted(base.filter(function (d) { return matches(d, state.filter, today); }));
    document.getElementById("list").innerHTML = shown.map(function (d) { return card(d, today); }).join("");
    // 모바일 '필터 · 정렬' 버튼 안에 접힌 조건 중 기본값이 아닌 것의 수
    var folded = [state.kind !== "all", state.section === "hotel" && state.scope !== "all", state.airline !== "all",
      state.sort !== "default", state.section === "flight" && !state.hideOther].filter(Boolean).length;
    var fn = document.getElementById("filter-n");
    fn.hidden = !folded; fn.textContent = folded;
    var conds = activeConditions();
    document.getElementById("active").hidden = !conds.length;
    document.getElementById("active-text").textContent = "적용된 조건: " + conds.join(" · ") + " · " + shown.length + "건";
    // 진행 여부 미확인: 마감일을 모르고 기사가 끊긴 지 오래된 행사. 지금 조건(탭·검색 등)에 맞는 것만 접어서 보여준다
    var stale = state.filter === "all" ? sorted(base.filter(function (d) { return d._status === "stale"; })) : [];
    var staleBox = document.getElementById("stale");
    staleBox.hidden = !stale.length;
    document.getElementById("stale-n").textContent = stale.length;
    document.getElementById("stale-list").innerHTML = stale.map(function (d) { return card(d, today); }).join("");
    var empty = document.getElementById("empty");
    empty.hidden = shown.length > 0 || stale.length > 0;
    empty.innerHTML = esc(SECTIONS[state.section].empty) +
      (conds.length ? ' <button type="button" class="reset" data-reset>조건 초기화</button>' : "");
  }

  // ---------------------------------------------------------------- 출발 시간표
  var DOW = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"];
  var sch = null;        // flights.json
  var schError = null;
  var schState = { date: null, dest: null, destAirline: "all", q: "", airline: "all", related: false, showAll: false };
  var DEST_PREVIEW = 12; // 도착지 카드를 처음에 이만큼만 보여준다

  function weekdayIdx(iso) { return (new Date(iso + "T00:00:00Z").getUTCDay() + 6) % 7; } // 월=0

  // 빠른 날짜: 오늘(0)·내일(1)·이번 주말(오늘이 토·일이면 오늘, 아니면 다가오는 토요일)
  function quickDate(key) {
    var today = todayKst(), add;
    if (key === "weekend") {
      var wd = weekdayIdx(today); // 월=0 … 토=5, 일=6
      add = wd >= 5 ? 0 : 5 - wd;
    } else {
      add = Number(key);
    }
    return new Date(Date.parse(today) + add * DAY).toISOString().slice(0, 10);
  }

  function flightsOn(iso) {
    var wd = weekdayIdx(iso);
    return sch.schedule.filter(function (r) { return r.first <= iso && iso <= r.last && r.days.charAt(wd) === "1"; });
  }

  // 탭 숫자: 오늘 실제 운항편 수 (공동운항 판매 편명 제외)
  function countToday() {
    return flightsOn(todayKst()).filter(function (f) { return !f.codeshare_of; }).length;
  }

  function prefixOf(flight) { return String(flight).slice(0, 2).toUpperCase(); }
  function normFlight(q) { return String(q).toUpperCase().replace(/\s+/g, ""); }
  var FLIGHT_NO = /^[A-Z0-9]{2}\d{1,4}[A-Z]?$/;

  // 날짜의 시간표 확보 상태: full(정기 일정 확보) | partial(일부 편만 공개) | none(미확보)
  function coverageOf(iso) {
    var cov = sch.coverage;
    return iso <= cov.full_until ? "full" : iso <= cov.partial_until ? "partial" : "none";
  }

  function activeAirDeals() {
    return deals.filter(function (d) { return sectionOf(d) !== "hotel" && d._status !== "ended" && d._status !== "stale" && (d.iata || []).length; });
  }

  // 행사와 운항편 연결. 할인이 이 편에 적용된다는 뜻은 아니다.
  //  related(관련 행사): 운항 항공사 코드 + 행사 노선의 출발지(인천) + 도착지가 모두 일치하고, 탑승 기간을 알면 그 안
  //  airline(항공사 진행 행사): 운항 또는 판매 항공사만 같은 행사. 노선이 다르거나 확인되지 않은 것
  function matchDeals(op, sellers, iso, airDeals) {
    var related = [], airline = [];
    var opCode = prefixOf(op.flight);
    airDeals.forEach(function (d) {
      var codes = d.iata;
      var byOperator = codes.indexOf(opCode) >= 0;
      var seller = sellers.filter(function (c) { return codes.indexOf(prefixOf(c.flight)) >= 0; })[0];
      if (!byOperator && !seller) return;
      var inTravel = !((d.travel_start && iso < d.travel_start) || (d.travel_end && iso > d.travel_end));
      var routeHit = (d.routes || []).some(function (r) {
        var dest = r.destination || "";
        return r.origin === "인천(ICN)" && (dest.indexOf("(" + op.dest_code + ")") >= 0 || dest === op.dest);
      });
      if (byOperator && routeHit && inTravel) related.push(d);
      else airline.push({ d: d, via: byOperator ? null : seller.flight });
    });
    return { related: related, airline: airline };
  }

  // 그 날짜의 실제 운항편 목록. 공동운항 판매 편명은 실제 운항편 아래 sellers로 묶는다.
  function operatingFlights(iso) {
    var all = flightsOn(iso), st = (sch.status || {})[iso] || {}, airDeals = activeAirDeals();
    var byFlight = {};
    all.forEach(function (f) { byFlight[f.flight] = f; });
    var sellers = {};
    all.forEach(function (f) {
      if (f.codeshare_of && byFlight[f.codeshare_of]) (sellers[f.codeshare_of] = sellers[f.codeshare_of] || []).push(f);
    });
    // 실제 운항편이 정기 일정에 없는 공동운항 편명은 그 편명 그대로 한 줄로 둔다
    return all.filter(function (f) { return !f.codeshare_of || !byFlight[f.codeshare_of]; }).map(function (f) {
      var sl = sellers[f.flight] || [];
      var m = matchDeals(f, sl, iso, airDeals);
      return { f: f, sellers: sl, s: st[f.flight] || (f.codeshare_of ? st[f.codeshare_of] : undefined), rel: m.related, air: m.airline };
    });
  }

  function airlineFilterOk(x) {
    var a = schState.airline;
    return a === "all" || x.f.airline === a || x.sellers.some(function (c) { return c.airline === a; });
  }

  function fillSelect(id, values, label) {
    var sel = document.getElementById(id), cur = sel.value;
    sel.innerHTML = '<option value="all">' + label + "</option>" + values.map(function (v) {
      return '<option value="' + esc(v[0]) + '">' + esc(v[1]) + "</option>";
    }).join("");
    sel.value = values.some(function (v) { return v[0] === cur; }) ? cur : "all";
    return sel.value;
  }

  function groupByDest(list) {
    var by = {};
    list.forEach(function (x) {
      var g = by[x.f.dest_code] || (by[x.f.dest_code] = { code: x.f.dest_code, name: x.f.dest, items: [], airlines: {}, rel: {}, air: {} });
      g.items.push(x);
      g.airlines[x.f.airline] = (g.airlines[x.f.airline] || 0) + 1;
      x.rel.forEach(function (d) { g.rel[d.id] = d; });
      x.air.forEach(function (a) { g.air[a.d.id] = a.d; });
    });
    return Object.keys(by).map(function (k) { return by[k]; });
  }

  function destCard(g) {
    var times = g.items.map(function (x) { return x.f.time; }).sort();
    var al = Object.keys(g.airlines).sort(function (a, b) { return g.airlines[b] - g.airlines[a]; });
    var nrel = Object.keys(g.rel).length, nair = Object.keys(g.air).length;
    return '<button type="button" class="dest" data-dest="' + esc(g.code) + '">' +
      '<span class="dest-top"><span class="dest-name">' + esc(g.name) + "<small>" + esc(g.code) + "</small></span>" +
      '<span class="dest-count">' + g.items.length + "편</span></span>" +
      '<span class="dest-sub">첫 편 ' + times[0] + " · 마지막 " + times[times.length - 1] + "</span>" +
      '<span class="dest-sub">' + esc(al.slice(0, 3).join(" · ")) + (al.length > 3 ? " 외 " + (al.length - 3) + "곳" : "") + "</span>" +
      (nrel || nair ? '<span class="pills">' +
        (nrel ? '<span class="pill green">노선 일치 행사 ' + nrel + "건</span>" : "") +
        (nair ? '<span class="pill gray">항공사 진행 행사 ' + nair + "건</span>" : "") + "</span>" : "") +
      "</button>";
  }

  // 행사 이름은 최신 기사로, 옆에 항공사 공식 페이지와 기사에 나온 판매처(여행사·플랫폼) 링크
  function dealLinks(d) {
    var links = [];
    if (d.official_url) links.push('<a href="' + esc(d.official_url) + '" target="_blank" rel="noopener" title="' + officialLabel(d) + '">' + esc(d.airline) + " 공식 ↗</a>");
    (d.agencies || []).forEach(function (g) {
      links.push('<a href="' + esc(g.url) + '" target="_blank" rel="noopener" title="기사 제목에 나온 판매처">' + esc(g.name) + " ↗</a>");
    });
    return links.length ? '<span class="deal-links">' + links.join(" · ") + "</span>" : "";
  }

  function dealName(d) {
    var a = d.articles && d.articles[0];
    var name = esc((d.event_name || d.headline).slice(0, 22));
    return '<span class="deal-item">' +
      (a ? '<a href="' + esc(a.url) + '" target="_blank" rel="noopener" title="근거 기사: ' + esc(a.title) + '">' + name + "</a>" : name) +
      dealLinks(d) + "</span>";
  }

  function dealCell(x) {
    var out = "";
    if (x.rel.length) out += '<span class="deal-rel">노선 일치 행사</span>' + x.rel.map(dealName).join("<br>");
    if (x.air.length) {
      // 노선이 확인되지 않은 행사라 접어 둔다
      out += '<details class="deal-air"><summary>항공사 진행 행사 ' + x.air.length + "건</summary>" + x.air.map(function (a) {
        return dealName(a.d) + (a.via ? ' <span class="cs">판매 편명 ' + esc(a.via) + " 기준</span>" : "");
      }).join("<br>") + "</details>";
    }
    return out;
  }

  function flightRow(x, iso, searched) {
    var f = x.f, s = x.s;
    var changed = s && s.estimated && (s.estimated !== f.time || s.estimated_day !== iso)
      ? (s.estimated_day !== iso ? md(s.estimated_day) + " " : "") + s.estimated : "";
    var state = s ? esc(s.remark || "예정") : "정기 일정";
    var share;
    if (x.sellers.length) {
      share = "공동운항 판매: " + x.sellers.slice(0, 3).map(function (c) {
        var hit = searched && c.flight === searched;
        return (hit ? "<mark>" : "") + esc(c.airline) + " " + esc(c.flight) + (hit ? "</mark>" : "");
      }).join(" · ") + (x.sellers.length > 3 ? " 외 " + (x.sellers.length - 3) + "편" : "");
    } else if (f.codeshare_of) {
      share = "공동운항 판매 편명 · 실제 운항 " + esc(f.codeshare_of) + " (정기 일정에 없음)";
    } else if (!f.status_seen) {
      share = "공동운항 여부 미확인";
    } else {
      share = "";
    }
    var deal = dealCell(x);
    return '<tr><td class="t">' + f.time + (changed ? '<span class="chg">→ ' + esc(changed) + "</span>" : "") + "</td>" +
      "<td><b>" + esc(f.airline) + " " + esc(f.flight) + '</b><span class="cs">운항 항공사</span>' +
        (share ? '<span class="cs">' + share + "</span>" : "") +
        (deal ? '<span class="rel-inline">' + deal + "</span>" : "") + "</td>" +
      '<td class="st' + (s ? "" : " muted") + '">' + state + "</td>" +
      '<td class="rel' + (deal ? "" : " muted") + '">' + (deal || "–") + "</td></tr>";
  }

  function renderSchedule() {
    var meta = document.getElementById("sch-meta"), warn = document.getElementById("sch-warn");
    var empty = document.getElementById("sch-empty");
    var listBox = document.getElementById("sch-list"), detail = document.getElementById("sch-detail");
    if (!sch) {
      meta.textContent = schError ? "시간표 데이터를 불러오지 못했습니다 (" + schError + ")." : "불러오는 중…";
      listBox.hidden = detail.hidden = true;
      return;
    }
    var cov = sch.coverage, today = todayKst(), sr = sch.status_range;
    var input = document.getElementById("sch-date");
    var maxDay = new Date(Date.parse(today) + 365 * DAY).toISOString().slice(0, 10);
    input.min = today; input.max = maxDay;
    if (!schState.date || schState.date < today || schState.date > maxDay) schState.date = today;
    input.value = schState.date;
    meta.innerHTML = "마지막 수집 " + esc(sch.generated_at.slice(0, 16).replace("T", " ")) + " KST · 시각은 " + esc(sch.timezone) +
      "<br>시간표 확보: " + md(today) + " ~ " + md(cov.full_until) +
      (cov.partial_until > cov.full_until ? " · 일부 편만 공개: ~ " + md(cov.partial_until) : "") +
      " · 그 뒤는 미확보 · 지연·변경 시각: " + (sr ? md(sr.from) + " ~ " + md(sr.to) : "이번 수집에서 받지 못함") +
      // 운항 현황을 못 받아 직전 수집분을 이어 쓴 경우 (collector/flights.py reuse_previous)
      (sch.status_from && sr ? " (이번 수집 실패, " + esc(sch.status_from.slice(5, 16).replace("-", "/").replace("T", " ")) + " 수집분)" : "");

    var iso = schState.date, cv = coverageOf(iso);
    document.querySelectorAll(".quick [data-day]").forEach(function (b) {
      b.setAttribute("aria-pressed", String(quickDate(b.dataset.day) === iso));
    });
    var covPill = document.getElementById("sch-cov");
    covPill.textContent = cv === "full" ? "시간표 확보" : cv === "partial" ? "일정 일부만 확인" : "시간표 미확보";
    covPill.className = "pill " + (cv === "full" ? "green" : cv === "partial" ? "orange" : "gray");
    var msgs = [];
    if (cv === "partial") msgs.push("시간표 일부만 확보: " + md(iso) + "은 다음 시즌 정기편 일정이 아직 공개되지 않아, 공개된 일부 편만 보입니다. 목록에 없는 노선도 운항할 수 있습니다.");
    if (cv === "none") msgs.push("시간표 미확보: " + md(iso) + "은 공개된 운항 일정이 없습니다. 운항편이 없다는 뜻이 아닙니다.");
    if (cv !== "none" && (!sr || iso < sr.from || iso > sr.to)) msgs.push("이 날짜는 지연·결항·변경 시각이 제공되지 않아 정기 예정 시각만 보여줍니다.");
    if ((Date.now() - Date.parse(sch.generated_at)) / 3600000 > STALE_HOURS) msgs.push("시간표 마지막 수집이 " + STALE_HOURS + "시간보다 오래됐습니다.");
    warn.hidden = !msgs.length;
    warn.innerHTML = msgs.map(esc).join("<br>");

    var ops = operatingFlights(iso), airlines = {};
    ops.forEach(function (x) { airlines[x.f.airline] = 1; x.sellers.forEach(function (c) { airlines[c.airline] = 1; }); });
    schState.airline = fillSelect("sch-airline", Object.keys(airlines).sort(function (a, b) { return a.localeCompare(b, "ko"); }).map(function (k) { return [k, k]; }), "전체 (운항·판매)");
    var list = ops.filter(airlineFilterOk);
    var noneMsg = cv === "full" ? "운항편 없음 (이 날짜 정기 일정 기준)" : cv === "partial" ? "공개된 일부 편 중에는 없음 · 시간표 일부만 확보" : "시간표 미확보 · 운항편이 없다는 뜻이 아닙니다";

    // 편명 검색: 운항 편명이든 공동운항 판매 편명이든 찾는다
    var q = normFlight(schState.q);
    if (FLIGHT_NO.test(q)) {
      var hits = list.filter(function (x) { return x.f.flight === q || x.sellers.some(function (c) { return c.flight === q; }); });
      listBox.hidden = true; detail.hidden = false;
      document.getElementById("sch-back").hidden = true;
      var h = hits[0], viaSeller = h && h.f.flight !== q;
      document.getElementById("sch-title").textContent = "편명 " + q + " · " + md(iso) +
        (h ? (viaSeller ? " · 공동운항 판매 편명 (실제 운항 " + h.f.airline + " " + h.f.flight + ")" : "") : "");
      document.getElementById("sch-body").innerHTML = hits.map(function (x) { return flightRow(x, iso, q); }).join("");
      empty.hidden = hits.length > 0;
      empty.textContent = q + " — " + noneMsg;
      document.getElementById("n-flights").textContent = countToday();
      return;
    }
    document.getElementById("sch-back").hidden = false;

    var groups = groupByDest(list);
    var picked = schState.dest && groups.filter(function (g) { return g.code === schState.dest; })[0];
    if (schState.dest && !picked) schState.dest = null; // 그 날짜·항공사에 해당 도착지 편이 없으면 목록으로

    listBox.hidden = !!picked;
    detail.hidden = !picked;
    if (picked) {
      picked.items.sort(function (a, b) { return a.f.time < b.f.time ? -1 : a.f.time > b.f.time ? 1 : 0; });
      document.getElementById("sch-title").textContent = picked.name + " (" + picked.code + ") · " + md(iso) + " · 실제 운항 " + picked.items.length + "편" +
        (cv === "full" ? "" : " · 시간표 일부만 확보");
      // 이 노선 항공사 버튼: 운항 편수 많은 순. 공동운항으로 파는 항공사도 넣는다(위 '항공사 (운항·판매)'와 같은 기준)
      var carriers = {};
      picked.items.forEach(function (x) {
        carriers[x.f.airline] = carriers[x.f.airline] || { op: 0, all: 0 };
        carriers[x.f.airline].op++;
        var who = {};
        who[x.f.airline] = 1;
        x.sellers.forEach(function (c) { who[c.airline] = 1; });
        Object.keys(who).forEach(function (n) { (carriers[n] = carriers[n] || { op: 0, all: 0 }).all++; });
      });
      if (!carriers[schState.destAirline]) schState.destAirline = "all";
      var order = Object.keys(carriers).sort(function (a, b) {
        return carriers[b].op - carriers[a].op || carriers[b].all - carriers[a].all || a.localeCompare(b, "ko");
      });
      var chip = function (key, label, n, title, codeshareOnly) {
        return '<button type="button"' + (codeshareOnly ? ' class="cs-only"' : "") + ' data-carrier="' + esc(key) + '" aria-pressed="' + (schState.destAirline === key) + '"' +
          (title ? ' title="' + esc(title) + '"' : "") + ">" + esc(label) + " <b>" + n + "</b></button>";
      };
      document.getElementById("sch-carriers").innerHTML = order.length > 1
        ? chip("all", "전체", picked.items.length) + order.map(function (n) {
            var c = carriers[n];
            return chip(n, n, c.all, c.op ? (c.all > c.op ? "직접 운항 " + c.op + "편 · 공동운항 판매 포함 " + c.all + "편" : "") : "공동운항 판매만 (직접 운항 없음)", !c.op);
          }).join("")
        : "";
      var rows = picked.items.filter(function (x) {
        var a = schState.destAirline;
        return (!schState.related || x.rel.length) &&
          (a === "all" || x.f.airline === a || x.sellers.some(function (c) { return c.airline === a; }));
      });
      document.getElementById("sch-body").innerHTML = rows.map(function (x) { return flightRow(x, iso); }).join("");
      empty.hidden = rows.length > 0;
      empty.textContent = schState.related ? "노선 일치 행사가 있는 운항편이 없습니다." : "이 항공사의 운항편이 없습니다.";
    } else {
      var ql = schState.q.toLowerCase();
      var shown = groups.filter(function (g) {
        return (!ql || g.name.toLowerCase().indexOf(ql) >= 0 || g.code.toLowerCase().indexOf(ql) >= 0) &&
          (!schState.related || Object.keys(g.rel).length);
      }).sort(function (a, b) {
        return Object.keys(b.rel).length - Object.keys(a.rel).length || b.items.length - a.items.length || a.name.localeCompare(b.name, "ko");
      });
      var limit = schState.showAll || ql ? shown.length : DEST_PREVIEW;
      document.getElementById("sch-dests").innerHTML = shown.slice(0, limit).map(destCard).join("");
      var more = document.getElementById("sch-more");
      more.hidden = (shown.length <= limit && !schState.showAll) || !!ql;
      more.textContent = schState.showAll ? "운항편 많은 " + DEST_PREVIEW + "곳만 보기" : "도착지 " + shown.length + "곳 모두 보기";
      empty.hidden = shown.length > 0;
      empty.textContent = schState.related ? "노선 일치 행사가 있는 도착지가 없습니다." : (ql ? "'" + schState.q + "' 도착 — " : "") + noneMsg;
    }
    document.getElementById("n-flights").textContent = countToday();
  }

  // 탭을 바꾸면 그 종류에 맞게 구분·항공사(브랜드) 선택지와 검색 안내를 다시 만든다.
  // params(주소의 조건)가 있으면 선택지를 만든 뒤 그 조건을 적용한다
  function setSection(sec, params) {
    var isSch = sec === "flights";
    document.querySelectorAll(".deal-view").forEach(function (el) { el.hidden = isSch; });
    document.getElementById("schedule").hidden = !isSch;
    if (isSch) {
      state.section = sec;
      document.querySelectorAll("[data-section]").forEach(function (b) { b.setAttribute("aria-pressed", String(b.dataset.section === sec)); });
      try { history.replaceState(null, "", "#flights"); } catch (e) { /* 미리보기 등 */ }
      updateTabCounts();
      renderSchedule();
      return;
    }
    var conf = SECTIONS[sec];
    state.section = sec; state.filter = "all"; state.kind = "all"; state.airline = "all";
    var kind = document.getElementById("kind");
    kind.innerHTML = conf.kinds.map(function (k) { return '<option value="' + k[0] + '">' + k[1] + "</option>"; }).join("");
    document.getElementById("kind-field").hidden = conf.kinds.length === 0;
    document.getElementById("hide-other-field").hidden = sec !== "flight";
    document.getElementById("scope-field").hidden = sec !== "hotel";
    state.scope = "all"; document.getElementById("scope").value = "all";
    document.getElementById("airline-label").textContent = conf.who;
    document.getElementById("q").placeholder = conf.placeholder;
    var sel = document.getElementById("airline");
    sel.innerHTML = '<option value="all">전체</option>';
    var ids = {};
    deals.forEach(function (d) { if (sectionOf(d) === sec && d.airline_id !== "multi") ids[d.airline_id] = d.airline; });
    Object.keys(ids).sort(function (a, b) { return ids[a].localeCompare(ids[b], "ko"); }).forEach(function (id) {
      var o = document.createElement("option");
      o.value = id; o.textContent = ids[id];
      sel.appendChild(o);
    });
    if (params) applyParams(params);
    render(); // render가 주소도 갱신한다
  }

  function sortKey(d) {
    // 예고는 시작 임박순, 진행중은 마감 임박순, 나머지는 최근 기사순
    if (d._status === "upcoming") return d.sale_start;
    if (d._status === "live") return d.sale_end || "9999-12-31";
    return String(99999999 - Number(d.last_published.replace(/-/g, "")));
  }

  // 수집 실패·중단을 화면에서 바로 알 수 있게 한다
  function showHealth(data) {
    var msgs = [];
    var ageH = (Date.now() - Date.parse(data.generated_at)) / 3600000;
    if (ageH > STALE_HOURS) {
      msgs.push("마지막 수집이 " + Math.floor(ageH) + "시간 전입니다. 예약 실행이 멈췄을 수 있습니다 (GitHub Actions 확인).");
    }
    var st = data.stats || {};
    if (st.failed_queries > 0) {
      msgs.push("직전 수집에서 검색어 " + st.queries + "개 중 " + st.failed_queries + "개가 실패했습니다. 일부 행사가 빠졌을 수 있습니다.");
    }
    var box = document.getElementById("health");
    box.hidden = msgs.length === 0;
    box.innerHTML = msgs.map(function (m) { return "<p>" + esc(m) + "</p>"; }).join("");
  }

  function init(data) {
    var today = todayKst();
    deals = data.deals.map(function (d) { d._status = statusOf(d, today); return d; });
    deals.sort(function (a, b) {
      return ORDER[a._status] - ORDER[b._status] || (sortKey(a) < sortKey(b) ? -1 : sortKey(a) > sortKey(b) ? 1 : 0);
    });

    baselines = data.baselines || { flight: data.baseline_first_seen || "" };
    deals.forEach(function (d) { d._fresh = freshness(d); });
    document.getElementById("updated").textContent =
      "ICN AIR DEALS · 마지막 수집 " + data.generated_at.slice(0, 16).replace("T", " ") + " KST · 기사 " +
      data.stats.articles + "건 → 행사 " + data.deals.length + "건";
    showHealth(data);

    deals.forEach(function (d) { if (d.airline_id !== "multi") names[d.airline_id] = d.airline; });
    var h = parseHash();
    setSection(h.sec, h.p);
  }

  // 요약 타일과 툴바 버튼이 같은 필터를 쓴다. 켜진 타일을 다시 누르면 전체로 돌아간다.
  document.querySelectorAll("[data-filter]").forEach(function (b) {
    b.addEventListener("click", function () {
      var f = b.dataset.filter;
      state.filter = (b.classList.contains("stat") && state.filter === f) ? "all" : f;
      render();
    });
  });
  document.querySelectorAll("[data-section]").forEach(function (b) {
    b.addEventListener("click", function () { setSection(b.dataset.section); });
  });
  // 주소의 #domestic·#hotel을 직접 바꾸거나 뒤로 가기를 해도 탭이 따라간다
  // 조건이 담긴 주소를 붙여 넣어도 따라간다. #guide 같은 페이지 안 이동은 무시한다
  window.addEventListener("hashchange", function () {
    var h = parseHash();
    if (!deals.length || (h.raw && h.sec !== h.raw)) return;
    if (h.sec !== state.section) setSection(h.sec, h.p);
    else if (h.sec !== "flights") { applyParams(h.p); render(); }
  });
  document.getElementById("scope").addEventListener("change", function (e) { state.scope = e.target.value; render(); });
  document.getElementById("kind").addEventListener("change", function (e) { state.kind = e.target.value; render(); });
  document.getElementById("airline").addEventListener("change", function (e) { state.airline = e.target.value; render(); });
  document.getElementById("q").addEventListener("input", function (e) { state.q = e.target.value.trim(); render(); });
  document.getElementById("hide-other").addEventListener("change", function (e) { state.hideOther = e.target.checked; render(); });
  document.getElementById("sort").addEventListener("change", function (e) { state.sort = e.target.value; render(); });
  document.getElementById("filter-toggle").addEventListener("click", function (e) {
    var open = document.getElementById("deal-filters").classList.toggle("open");
    e.currentTarget.setAttribute("aria-expanded", String(open));
  });
  // 조건 초기화 버튼은 조건 줄과 빈 목록 안내 두 곳에 있다
  document.addEventListener("click", function (e) { if (e.target.closest("[data-reset]")) resetFilters(); });
  document.querySelectorAll(".quick [data-day]").forEach(function (b) {
    b.addEventListener("click", function () { schState.date = quickDate(b.dataset.day); schState.dest = null; renderSchedule(); });
  });

  document.getElementById("sch-date").addEventListener("change", function (e) { schState.date = e.target.value; renderSchedule(); });
  document.getElementById("sch-q").addEventListener("input", function (e) { schState.q = e.target.value.trim(); schState.dest = null; renderSchedule(); });
  document.getElementById("sch-airline").addEventListener("change", function (e) { schState.airline = e.target.value; renderSchedule(); });
  document.getElementById("sch-related").addEventListener("change", function (e) { schState.related = e.target.checked; renderSchedule(); });
  document.getElementById("sch-more").addEventListener("click", function () { schState.showAll = !schState.showAll; renderSchedule(); });
  document.getElementById("sch-back").addEventListener("click", function () { schState.dest = null; renderSchedule(); });
  document.getElementById("sch-carriers").addEventListener("click", function (e) {
    var b = e.target.closest("[data-carrier]");
    if (!b) return;
    schState.destAirline = b.dataset.carrier;
    renderSchedule();
  });
  document.getElementById("sch-dests").addEventListener("click", function (e) {
    var b = e.target.closest("[data-dest]");
    if (!b) return;
    schState.dest = b.dataset.dest;
    schState.destAirline = "all";
    renderSchedule();
    document.getElementById("schedule").scrollIntoView({ block: "start" });
  });

  // 시간표는 행사와 따로 불러온다. 없거나 실패해도 행사 화면은 그대로 쓴다
  fetch("flights.json", { cache: "no-store" })
    .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(function (data) {
      sch = data;
      destCache = {};
      if (state.section === "flights") renderSchedule();
      else {
        document.getElementById("n-flights").textContent = countToday();
        if (deals.length) render(); // 카드의 운항 도착지 블록을 채운다
      }
    })
    .catch(function (e) { schError = e.message; if (state.section === "flights") renderSchedule(); else if (deals.length) render(); });

  // Secret Flying 서울 출발 특가. 없거나 실패해도 나머지 화면은 그대로 쓴다
  fetch("secretflying.json", { cache: "no-store" })
    .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(function (data) { sf = data; if (deals.length) render(); })
    .catch(function () { sf = null; });

  fetch("deals.json", { cache: "no-store" })
    .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(init)
    .catch(function (e) {
      document.getElementById("updated").textContent = "ICN AIR DEALS · 데이터를 불러오지 못했습니다 (" + e.message + "). 잠시 후 새로고침하세요.";
    });
})();
