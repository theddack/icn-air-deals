// 상태 규칙은 collector/status.py와 같다. 페이지를 연 날(KST) 기준으로 다시 계산한다.
(function () {
  "use strict";

  var DAY = 86400000;
  var WEEK = ["일", "월", "화", "수", "목", "금", "토"];
  var STATUS_LABEL = { upcoming: "예고", live: "진행중", undated: "날짜 미상", ended: "마감" };
  var ORDER = { upcoming: 0, live: 1, undated: 2, ended: 3 };
  var ICN_LABEL = { yes: "인천 출발", no: "인천 외 출발", unknown: "출발지 미확인" };
  var VERIFY_LABEL = { official: "공식 확인", news: "뉴스 기반 · 미확인" };
  var NEW_HOURS = 48;   // 처음 본 지 이 시간 안이면 '신규', 기사가 이 시간 안에 더해졌으면 '기사 추가'
  var STALE_HOURS = 12; // 마지막 수집이 이보다 오래되면 수집이 멈춘 것으로 본다

  var state = { status: "all", kind: "all", airline: "all", q: "", hideOther: true };
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

  function travelText(d) {
    if (d.travel_start && d.travel_end) return "탑승 " + md(d.travel_start) + " ~ " + md(d.travel_end);
    if (d.travel_end) return "탑승 ~ " + md(d.travel_end) + "까지";
    return "";
  }

  function periodText(d) {
    if (d.sale_start && d.sale_end) return md(d.sale_start) + " ~ " + md(d.sale_end);
    if (d.sale_start) return md(d.sale_start) + " 시작 · 마감일 미상";
    if (d.sale_end) return "~ " + md(d.sale_end) + "까지 · 시작일 미상";
    return "기간 미상";
  }

  function card(d, today) {
    var st = d._status;
    var title = d.event_name ? d.event_name : d.headline;
    var fresh = freshness(d);
    var multi = d.airline_id === "multi";
    var who = multi ? "여러 항공사 · " + d.airlines_mentioned.join("·") : d.airline;
    var travel = travelText(d);
    var arts = d.articles.map(function (a) {
      return '<li><a href="' + esc(a.url) + '" target="_blank" rel="noopener">' + esc(a.title) + "</a>" +
        "<span>" + esc(a.outlet || "") + " · " + md(a.published) + "</span></li>";
    }).join("");
    return '<article class="deal s-' + st + '">' +
      '<span class="stripe" aria-hidden="true"></span>' +
      '<div class="main">' +
        '<div class="air"><b>' + esc(who) + "</b>" +
          (multi ? '<span class="tag warn">항공사 미분류</span>' : "") +
          '<span class="tag' + (d.from_icn === "yes" ? " icn" : "") + '">' + ICN_LABEL[d.from_icn] + "</span>" +
          (d.discount ? '<span class="disc">' + esc(d.discount) + "</span>" : "") +
        "</div>" +
        '<div class="title">' +
          (fresh === "new" ? '<span class="fresh">신규</span>' : fresh === "updated" ? '<span class="fresh soft">기사 추가</span>' : "") +
          esc(title) + "</div>" +
        '<div class="period">판매 ' + periodText(d) + (travel ? " · " + travel : "") + "</div>" +
        '<div class="src">' + VERIFY_LABEL[d.verification || "news"] +
          (d.official_url ? ' · <a href="' + esc(d.official_url) + '" target="_blank" rel="noopener">공식 페이지에서 확인</a>' : "") +
        "</div>" +
      "</div>" +
      '<div class="side"><span class="pill p-' + st + '">' + STATUS_LABEL[st] + "</span>" +
        '<span class="dday">' + ddayText(d, st, today) + "</span></div>" +
      "<details><summary>기사 " + d.articles.length + "건" +
        (d.event_name ? " · " + esc(d.headline) : "") + "</summary><ul>" + arts + "</ul></details>" +
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
    var counts = { all: base.length, upcoming: 0, live: 0, undated: 0, ended: 0 };
    base.forEach(function (d) { counts[d._status]++; });
    Object.keys(counts).forEach(function (k) { document.getElementById("c-" + k).textContent = counts[k]; });

    var shown = base.filter(function (d) { return state.status === "all" || d._status === state.status; });
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
    document.getElementById("updated").textContent =
      "마지막 수집 " + data.generated_at.slice(0, 16).replace("T", " ") + " KST · 기사 " +
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

  document.querySelectorAll(".chip").forEach(function (b) {
    b.addEventListener("click", function () {
      state.status = b.dataset.status;
      document.querySelectorAll(".chip").forEach(function (x) { x.setAttribute("aria-pressed", String(x === b)); });
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
      document.getElementById("updated").textContent = "데이터를 불러오지 못했습니다 (" + e.message + "). 잠시 후 새로고침하세요.";
    });
})();
