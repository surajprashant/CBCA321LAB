/* Shared helpers for all pages. */
const DCV = (() => {
  // Categorical slots in fixed order (validated for colour-blind separation).
  // A contributor's slot = their all-time rank, so colours never shift when filtering.
  const PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"];
  const NEUTRAL = "#a9a8a2";
  // One-hue sequential ramp (light -> dark) for the heatmap.
  const RAMP = ["#efeeea", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"];
  const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  const SURFACE = "#fcfcfb";

  const colorFor = (index) => (index === null || index === undefined || index >= PALETTE.length)
    ? NEUTRAL : PALETTE[index];

  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const fmt = (n) => (n ?? 0).toLocaleString("en-IN");

  const initials = (name) => (name || "?").split(/\s+/).filter(Boolean).slice(0, 2)
    .map((part) => part[0].toUpperCase()).join("");

  async function api(path, options = {}) {
    const res = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    if (res.status === 204) return null;
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.error || `Request failed (${res.status})`);
    return body;
  }

  let toastTimer;
  function toast(message, isError = false) {
    let el = document.querySelector(".toast");
    if (!el) {
      el = document.createElement("div");
      el.className = "toast";
      el.setAttribute("role", "status");
      document.body.appendChild(el);
    }
    el.textContent = message;
    el.classList.toggle("error", isError);
    el.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove("show"), isError ? 5000 : 2800);
  }

  // ------------------------------------------------------------------ tooltip
  const tip = document.createElement("div");
  tip.className = "tooltip";
  document.addEventListener("DOMContentLoaded", () => document.body.appendChild(tip));
  function showTip(event, html) {
    tip.innerHTML = html;
    tip.style.display = "block";
    const x = Math.min(event.clientX + 12, window.innerWidth - tip.offsetWidth - 8);
    tip.style.left = `${x}px`;
    tip.style.top = `${event.clientY - tip.offsetHeight - 10}px`;
  }
  const hideTip = () => { tip.style.display = "none"; };

  // ------------------------------------------------------------------ date range in the URL
  function getRange() {
    const params = new URLSearchParams(location.search);
    return { since: params.get("since") || "", until: params.get("until") || "" };
  }
  function setRange(range) {
    const params = new URLSearchParams(location.search);
    ["since", "until"].forEach((key) => (range[key] ? params.set(key, range[key]) : params.delete(key)));
    const query = params.toString();
    history.replaceState(null, "", location.pathname + (query ? `?${query}` : ""));
  }
  function rangeQuery(extra = {}) {
    const params = new URLSearchParams();
    const range = getRange();
    if (range.since) params.set("since", range.since);
    if (range.until) params.set("until", range.until);
    Object.entries(extra).forEach(([k, v]) => v !== undefined && v !== null && params.set(k, v));
    const query = params.toString();
    return query ? `?${query}` : "";
  }

  /* Filter bar: presets are counted back from the repo's LAST commit (not today),
     so "Last 90 days" is meaningful even for a project that went quiet. */
  function buildFilters(container, anchorDay, onChange) {
    const presets = [["All time", null], ["Last 30 days", 30], ["Last 90 days", 90], ["Last year", 365]];
    container.innerHTML = `
      <div class="seg" role="group" aria-label="Date range presets">
        ${presets.map(([label, days]) => `<button type="button" data-days="${days ?? ""}">${label}</button>`).join("")}
      </div>
      <label for="f-since">From</label><input type="date" id="f-since">
      <label for="f-until">to</label><input type="date" id="f-until">
      <button type="button" id="f-apply">Apply</button>
      <span class="spacer"></span>
      <span class="muted" id="f-note"></span>`;
    const since = container.querySelector("#f-since");
    const until = container.querySelector("#f-until");
    const buttons = [...container.querySelectorAll(".seg button")];

    const sync = () => {
      const range = getRange();
      since.value = range.since;
      until.value = range.until;
      const anchor = anchorDay ? new Date(`${anchorDay}T00:00:00`) : null;
      buttons.forEach((b) => {
        const days = b.dataset.days;
        let active = false;
        if (!days) active = !range.since && !range.until;
        else if (anchor && range.until === anchorDay) {
          const start = new Date(anchor);
          start.setDate(start.getDate() - Number(days) + 1);
          active = range.since === isoDay(start);
        }
        b.classList.toggle("active", active);
      });
      container.querySelector("#f-note").textContent =
        range.since || range.until ? `Showing ${range.since || "start"} → ${range.until || "latest"}` : "";
    };

    buttons.forEach((b) => b.addEventListener("click", () => {
      const days = b.dataset.days;
      if (!days || !anchorDay) setRange({});
      else {
        const start = new Date(`${anchorDay}T00:00:00`);
        start.setDate(start.getDate() - Number(days) + 1);
        setRange({ since: isoDay(start), until: anchorDay });
      }
      sync();
      onChange();
    }));
    container.querySelector("#f-apply").addEventListener("click", () => {
      if (since.value && until.value && since.value > until.value) {
        toast("'From' date must be before 'to' date", true);
        return;
      }
      setRange({ since: since.value, until: until.value });
      sync();
      onChange();
    });
    sync();
  }

  function isoDay(d) {
    const pad = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  }

  // ------------------------------------------------------------------ KPI tiles
  function renderKpis(container, items) {
    container.innerHTML = items.map((item) => `
      <div class="card kpi">
        <div class="label">${esc(item.label)}</div>
        <div class="value">${item.html ?? esc(item.value)}</div>
        ${item.note ? `<div class="note">${item.note}</div>` : ""}
      </div>`).join("");
  }

  // ------------------------------------------------------------------ heatmap (7 x 24)
  function renderHeatmap(container, data) {
    const max = data.max || 0;
    const level = (n) => (n === 0 || max === 0) ? 0 : Math.min(RAMP.length - 1, Math.ceil((n / max) * (RAMP.length - 1)));
    let html = `<div></div>`;
    for (let h = 0; h < 24; h++) html += `<div class="hl">${h % 3 === 0 ? h : ""}</div>`;
    data.matrix.forEach((row, d) => {
      html += `<div class="rl">${DAYS[d]}</div>`;
      row.forEach((n, h) => {
        html += `<div class="cell" style="background:${RAMP[level(n)]}" data-d="${d}" data-h="${h}" data-n="${n}"
                  aria-label="${DAYS[d]} ${h}:00 – ${n} commits"></div>`;
      });
    });
    container.innerHTML = `<div class="heatmap">${html}</div>
      <div class="legend-ramp">Fewer ${RAMP.map((c) => `<i style="background:${c}"></i>`).join("")} More</div>`;
    container.querySelectorAll(".cell").forEach((cell) => {
      cell.addEventListener("mousemove", (e) => {
        const h = Number(cell.dataset.h);
        const n = Number(cell.dataset.n);
        showTip(e, `<b>${DAYS[cell.dataset.d]} ${String(h).padStart(2, "0")}:00–${String(h).padStart(2, "0")}:59</b><br>${n} commit${n === 1 ? "" : "s"}`);
      });
      cell.addEventListener("mouseleave", hideTip);
    });
  }

  const peakText = (peak) => peak
    ? `Busiest slot: ${DAYS[peak.weekday]} ${String(peak.hour).padStart(2, "0")}:00 (${peak.commits} commit${peak.commits === 1 ? "" : "s"})`
    : "No commits in this range";

  // ------------------------------------------------------------------ timeline chart
  function timelineChart(canvas, data, previous) {
    if (previous) previous.destroy();
    const labels = data.labels.map((l) => formatBucket(l, data.granularity));
    const datasets = data.series.map((s) => ({
      label: s.name,
      data: s.data,
      backgroundColor: colorFor(s.color_index),
      borderColor: SURFACE,
      borderWidth: { top: data.series.length > 1 ? 2 : 0 },
      borderSkipped: "bottom",
      borderRadius: 3,
      maxBarThickness: 36,
    }));
    return new Chart(canvas, {
      type: "bar",
      data: { labels, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 250 },
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: {
            display: data.series.length > 1,
            position: "top",
            align: "start",
            labels: { usePointStyle: true, pointStyle: "rectRounded", boxWidth: 10, color: "#52514e", font: { size: 12 } },
          },
          tooltip: {
            backgroundColor: "#0b0b0b",
            padding: 10,
            usePointStyle: true,
            filter: (item) => item.raw > 0,
            callbacks: {
              title: (items) => items.length ? bucketTitle(data.labels[items[0].dataIndex], data.granularity) : "",
              label: (item) => ` ${item.dataset.label}: ${item.raw} commit${item.raw === 1 ? "" : "s"}`,
              footer: (items) => items.length > 1 ? `Total: ${items.reduce((a, i) => a + i.raw, 0)}` : "",
            },
          },
        },
        scales: {
          x: { stacked: true, grid: { display: false }, ticks: { color: "#7d7c77", maxRotation: 0, autoSkipPadding: 16 } },
          y: { stacked: true, beginAtZero: true, grid: { color: "#ecebe8" }, border: { display: false },
               ticks: { color: "#7d7c77", precision: 0 }, title: { display: true, text: "Commits", color: "#7d7c77" } },
        },
      },
    });
  }

  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  function formatBucket(label, granularity) {
    if (granularity === "month") {
      const [y, m] = label.split("-");
      return `${MONTHS[Number(m) - 1]} ${y.slice(2)}`;
    }
    const [, m, d] = label.split("-");
    return `${Number(d)} ${MONTHS[Number(m) - 1]}`;
  }
  function bucketTitle(label, granularity) {
    if (granularity === "month") {
      const [y, m] = label.split("-");
      return `${MONTHS[Number(m) - 1]} ${y}`;
    }
    const [y, m, d] = label.split("-");
    const text = `${Number(d)} ${MONTHS[Number(m) - 1]} ${y}`;
    return granularity === "week" ? `Week of ${text}` : text;
  }

  return { PALETTE, colorFor, esc, fmt, initials, api, toast, getRange, rangeQuery,
           buildFilters, renderKpis, renderHeatmap, peakText, timelineChart, showTip, hideTip };
})();
