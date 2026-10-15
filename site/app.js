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

  var state = { filter: "all", kind: "all", airline: "all", q: "", hideOther: true };
  var deals = [];
  var names = {};       // airline_id -> 이름 (필터용)
  var baseline = null;  // 첫 수집 시각. 이때 들어온 기사는 신규로 보지 않는다

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

  function freshness(d) {
    var now = Date.now(), win = NEW_HOURS * 3600000;
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

  function row(label, value, cls) {
    return "<dt>" + label + "</dt><dd" + (cls ? ' class="' + cls + '"' : "") + ">" + value + "</dd>";
  }

  function card(d, today) {
    var st = d._status;
    var title = d.event_name ? d.event_name : d.headline;
    var multi = d.airline_id === "multi";
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
      (multi ? '<span class="pill orange">항공사 미분류</span>' : "");
    var airline = multi ? "여러 항공사 (" + esc(d.airlines_mentioned.join("·")) + ")" : esc(d.airline);
    return '<article class="deal' + (st === "ended" ? " ended" : "") + '">' +
      '<div class="pills">' + pills + "</div>" +
      "<h3>" + esc(title) + "</h3>" +
      (d.discount ? '<div class="price">' + esc(d.discount) + "</div>" : '<div class="price none">할인 정보 미확인</div>') +
      "<dl>" +
        row("항공사", airline) +
        row("판매 기간", sale || "미확인", sale ? "" : "unk") +
        row("탑승 기간", travel || "미확인", travel ? "" : "unk") +
        row("출발 공항", ICN_LABEL[d.from_icn], d.from_icn === "yes" ? "icn" : d.from_icn === "unknown" ? "unk" : "") +
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
    if (state.kind !== "all" && d.kind !== state.kind) return false;
    if (state.airline !== "all" && d.airline_id !== state.airline &&
        (d.airlines_mentioned || []).indexOf(names[state.airline]) < 0) return false;
    if (state.hideOther && d.from_icn === "no") return false;
    if (state.q) {
      var hay = (d.airline + " " + (d.event_name || "") + " " + d.articles.map(function (a) { return a.title; }).join(" ")).toLowerCase();
      if (hay.indexOf(state.q.toLowerCase()) < 0) return false;
    }
    return true;
  }

  function render() {
    var today = todayKst();
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
    document.getElementById("empty").hidden = shown.length > 0;
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

    baseline = data.baseline_first_seen || "";
    deals.forEach(function (d) { d._fresh = freshness(d); });
    document.getElementById("updated").textContent =
      "ICN AIR DEALS · 마지막 수집 " + data.generated_at.slice(0, 16).replace("T", " ") + " KST · 기사 " +
      data.stats.articles + "건 → 행사 " + data.deals.length + "건";
    showHealth(data);

    deals.forEach(function (d) { if (d.airline_id !== "multi") names[d.airline_id] = d.airline; });
    var sel = document.getElementById("airline");
    Object.keys(names).sort(function (a, b) { return names[a].localeCompare(names[b], "ko"); }).forEach(function (id) {
      var o = document.createElement("option");
      o.value = id; o.textContent = names[id];
      sel.appendChild(o);
    });
    render();
  }

  // 요약 타일과 툴바 버튼이 같은 필터를 쓴다. 켜진 타일을 다시 누르면 전체로 돌아간다.
  document.querySelectorAll("[data-filter]").forEach(function (b) {
    b.addEventListener("click", function () {
      var f = b.dataset.filter;
      state.filter = (b.classList.contains("stat") && state.filter === f) ? "all" : f;
      render();
    });
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
