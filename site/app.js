// 상태 규칙은 collector/status.py와 같다. 페이지를 연 날(KST) 기준으로 다시 계산한다.
(function () {
  "use strict";

  var DAY = 86400000;
  var WEEK = ["일", "월", "화", "수", "목", "금", "토"];
  var STATUS_LABEL = { upcoming: "판매 예정", live: "진행 중", undated: "날짜 미확인", ended: "마감" };
  var STATUS_PILL = { upcoming: "", live: "green", undated: "orange", ended: "gray" };
  var CLOSING_DAYS = 3; // 마감까지 이 일수 이내면 '마감 임박'
  var ORDER = { upcoming: 0, live: 1, undated: 2, ended: 3 };
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
    hotel: { kinds: [["all", "전체"], ["hotel", "호텔·리조트"], ["platform", "예약 플랫폼·여행사"], ["campaign", "정부 할인 행사"]], who: "브랜드",
             placeholder: "제주, 페스타, 호캉스…",
             empty: "조건에 맞는 숙박 행사가 없습니다. 필터를 바꿔 보세요." }
  };

  var state = { section: "flight", filter: "all", kind: "all", airline: "all", q: "", hideOther: true };
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
    var now = Date.now(), win = NEW_HOURS * 3600000, baseline = baselines[sectionOf(d)] || "";
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

  function routesText(d) {
    return (d.routes || []).map(function (r) {
      return esc(r.origin || "출발 미확인") + " → " + esc(r.destination || "도착 미확인");
    }).join(", ");
  }

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
      '<span class="pill ' + (verified ? "green" : "orange") + '">' + VERIFY_LABEL[d.verification || "news"] + "</span>" +
      (multi ? '<span class="pill orange">' + SECTIONS[sec].who + " 미분류</span>" : "");
    var airline = multi ? esc(d.airline) + " (" + esc(d.airlines_mentioned.join("·")) + ")" : esc(d.airline);
    var routes = routesText(d);
    var travelConflict = (d.conflicts || []).indexOf("travel") >= 0;
    var travelRow = travelConflict
      ? row(hotel ? "투숙 기간" : "탑승 기간", "출처 간 불일치 · 관련 기사 확인", "conflict")
      : row(hotel ? "투숙 기간" : "탑승 기간", travel || "미확인", travel ? "" : "unk", travel ? evLink(d, "travel") : "");
    var rows = hotel
      ? row("지역", (d.regions || []).length ? esc(d.regions.join(" · ")) : "미확인", (d.regions || []).length ? "" : "unk") +
        row("판매 기간", sale || "미확인", sale ? "" : "unk", sale ? evLink(d, "sale") : "") +
        travelRow +
        row("조건", (d.conditions || []).length ? esc(d.conditions.join(" · ")) : "미확인", (d.conditions || []).length ? "" : "unk")
      : row("노선", routes || (sec === "domestic" ? "국내선 · 구간 미확인" : "미확인"), routes ? "" : "unk", routes ? evLink(d, "route") : "") +
        row("판매 기간", sale || "미확인", sale ? "" : "unk", sale ? evLink(d, "sale") : "") +
        travelRow +
        (sec === "domestic" ? "" : row("출발 공항", ICN_LABEL[d.from_icn], d.from_icn === "yes" ? "icn" : d.from_icn === "unknown" ? "unk" : ""));
    return '<article class="deal' + (st === "ended" ? " ended" : "") + '">' +
      '<div class="pills">' + pills + "</div>" +
      "<h3>" + esc(title) + "</h3>" +
      (d.discount ? '<div class="price">' + esc(d.discount) + evLink(d, "discount") + "</div>" : '<div class="price none">할인 정보 미확인</div>') +
      "<dl>" +
        row(SECTIONS[sec].who, airline) +
        rows +
        row("남은 기간", st === "undated" ? "미확인 · 최근 기사 " + md(d.last_published) : ddayText(d, st, today), st === "undated" ? "unk" : "") +
      "</dl>" +
      '<div class="foot">' +
        '<div class="foot-row"><span>뉴스 기사에서 추출 · 조건은 공식 페이지 확인 필요</span>' +
          (d.official_url ? '<a href="' + esc(d.official_url) + '" target="_blank" rel="noopener">공식 페이지에서 확인 ↗</a>' : "") +
        "</div>" +
        "<details><summary>관련 기사 " + d.articles.length + "건" + (d.event_name ? " · " + esc(d.headline) : "") + "</summary><ul>" + arts + "</ul></details>" +
      "</div>" +
    "</article>";
  }

  function visible(d) {
    if (sectionOf(d) !== state.section) return false;
    if (state.kind !== "all" && d.kind !== state.kind) return false;
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
    Object.keys(SECTIONS).forEach(function (sec) {
      document.getElementById("n-" + sec).textContent = deals.filter(function (d) {
        return sectionOf(d) === sec && !(sec === "flight" && state.hideOther && d.from_icn === "no");
      }).length;
    });
    document.querySelectorAll("[data-section]").forEach(function (b) {
      b.setAttribute("aria-pressed", String(b.dataset.section === state.section));
    });
    var base = deals.filter(visible);
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
    var shown = base.filter(function (d) { return matches(d, state.filter, today); });
    document.getElementById("list").innerHTML = shown.map(function (d) { return card(d, today); }).join("");
    var empty = document.getElementById("empty");
    empty.hidden = shown.length > 0;
    empty.textContent = SECTIONS[state.section].empty;
  }

  // 탭을 바꾸면 그 종류에 맞게 구분·항공사(브랜드) 선택지와 검색 안내를 다시 만든다
  function setSection(sec) {
    var conf = SECTIONS[sec];
    state.section = sec; state.filter = "all"; state.kind = "all"; state.airline = "all";
    var kind = document.getElementById("kind");
    kind.innerHTML = conf.kinds.map(function (k) { return '<option value="' + k[0] + '">' + k[1] + "</option>"; }).join("");
    document.getElementById("kind-field").hidden = conf.kinds.length === 0;
    document.getElementById("hide-other-field").hidden = sec !== "flight";
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
    try { history.replaceState(null, "", sec === "flight" ? location.pathname + location.search : "#" + sec); } catch (e) { /* 미리보기 등 */ }
    render();
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
    var fromHash = location.hash.slice(1);
    setSection(SECTIONS[fromHash] ? fromHash : "flight");
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
  window.addEventListener("hashchange", function () {
    var sec = location.hash.slice(1);
    if (deals.length && (SECTIONS[sec] ? sec : "flight") !== state.section) setSection(SECTIONS[sec] ? sec : "flight");
  });
  document.getElementById("kind").addEventListener("change", function (e) { state.kind = e.target.value; render(); });
  document.getElementById("airline").addEventListener("change", function (e) { state.airline = e.target.value; render(); });
  document.getElementById("q").addEventListener("input", function (e) { state.q = e.target.value.trim(); render(); });
  document.getElementById("hide-other").addEventListener("change", function (e) { state.hideOther = e.target.checked; render(); });

  fetch("deals.json", { cache: "no-store" })
    .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(init)
    .catch(function (e) {
      document.getElementById("updated").textContent = "ICN AIR DEALS · 데이터를 불러오지 못했습니다 (" + e.message + "). 잠시 후 새로고침하세요.";
    });
})();
