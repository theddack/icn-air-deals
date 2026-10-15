// 상태 규칙은 collector/status.py와 같다. 페이지를 연 날(KST) 기준으로 다시 계산한다.
(function () {
  "use strict";

  var DAY = 86400000;
  var WEEK = ["일", "월", "화", "수", "목", "금", "토"];
  var STATUS_LABEL = { upcoming: "예고", live: "진행중", undated: "날짜 미상", ended: "마감" };
  var ORDER = { upcoming: 0, live: 1, undated: 2, ended: 3 };
  var ICN_LABEL = { yes: "인천 출발", no: "인천 외 출발", unknown: "출발지 미확인" };

  var state = { status: "all", kind: "all", airline: "all", q: "", hideOther: true };
  var deals = [];

  function todayKst() {
    return new Date(Date.now() + 9 * 3600000).toISOString().slice(0, 10);
  }
  function diffDays(a, b) { // a - b (일)
    return Math.round((Date.parse(a) - Date.parse(b)) / DAY);
  }
  function md(iso) {
    var d = new Date(iso + "T00:00:00Z");
    return (d.getUTCMonth() + 1) + "/" + d.getUTCDate() + "(" + WEEK[d.getUTCDay()] + ")";
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

  function periodText(d) {
    if (d.sale_start && d.sale_end) return md(d.sale_start) + " ~ " + md(d.sale_end);
    if (d.sale_start) return md(d.sale_start) + " 시작 · 마감일 미상";
    if (d.sale_end) return "~ " + md(d.sale_end) + "까지 · 시작일 미상";
    return "판매 기간 미상";
  }

  function card(d, today) {
    var st = d._status;
    var title = d.event_name ? d.event_name : d.headline;
    var arts = d.articles.map(function (a) {
      return '<li><a href="' + esc(a.url) + '" target="_blank" rel="noopener">' + esc(a.title) + "</a>" +
        "<span>" + esc(a.outlet || "") + " · " + md(a.published) + "</span></li>";
    }).join("");
    return '<article class="deal s-' + st + '">' +
      '<span class="stripe" aria-hidden="true"></span>' +
      '<div class="main">' +
        '<div class="air"><b>' + esc(d.airline) + "</b>" +
          '<span class="tag' + (d.from_icn === "yes" ? " icn" : "") + '">' + ICN_LABEL[d.from_icn] + "</span>" +
          (d.discount ? '<span class="disc">' + esc(d.discount) + "</span>" : "") +
        "</div>" +
        '<div class="title">' + esc(title) + "</div>" +
        '<div class="period">' + periodText(d) + "</div>" +
      "</div>" +
      '<div class="side"><span class="pill p-' + st + '">' + STATUS_LABEL[st] + "</span>" +
        '<span class="dday">' + ddayText(d, st, today) + "</span></div>" +
      "<details><summary>기사 " + d.articles.length + "건" +
        (d.event_name ? " · " + esc(d.headline) : "") + "</summary><ul>" + arts + "</ul></details>" +
      "</article>";
  }

  function visible(d) {
    if (state.kind !== "all" && d.kind !== state.kind) return false;
    if (state.airline !== "all" && d.airline_id !== state.airline) return false;
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

  function init(data) {
    var today = todayKst();
    deals = data.deals.map(function (d) { d._status = statusOf(d, today); return d; });
    deals.sort(function (a, b) {
      return ORDER[a._status] - ORDER[b._status] || (sortKey(a) < sortKey(b) ? -1 : sortKey(a) > sortKey(b) ? 1 : 0);
    });

    document.getElementById("updated").textContent =
      "마지막 수집 " + data.generated_at.slice(0, 16).replace("T", " ") + " KST · 기사 " +
      data.stats.articles + "건 → 행사 " + data.deals.length + "건";

    var names = {};
    deals.forEach(function (d) { names[d.airline_id] = d.airline; });
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
