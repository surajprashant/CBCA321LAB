/* Repository dashboard. */
(() => {
  const { api, esc, fmt, toast, colorFor, rangeQuery } = DCV;
  const repoId = document.body.dataset.repoId;
  const base = `/api/repos/${repoId}`;
  let sort = "commits";
  let chart = null;

  const el = (id) => document.getElementById(id);

  async function loadSummary() {
    const s = await api(`${base}/summary${rangeQuery()}`);
    const top = s.top_contributor;
    DCV.renderKpis(el("kpis"), [
      { label: "Commits", value: fmt(s.commits), note: s.merges ? `+ ${fmt(s.merges)} merges` : "no merges" },
      { label: "Contributors", value: fmt(s.contributors), note: top ? `${esc(top.name)} leads with ${top.share}%` : "—" },
      { label: "Lines changed", html: `<span class="plus">+${fmt(s.additions)}</span>`,
        note: `<span class="minus">−${fmt(s.deletions)}</span> deleted · net ${s.net_lines >= 0 ? "+" : ""}${fmt(s.net_lines)}` },
      { label: "Active days", value: fmt(s.active_days), note: s.first_day ? `${s.first_day} → ${s.last_day}` : "—" },
      { label: "Files touched", value: fmt(s.files_touched), note: "distinct paths" },
      { label: "Bus factor", value: s.bus_factor,
        note: s.bus_factor === 1 ? "one person did ≥ half the commits" : s.bus_factor ? `people covering ≥ 50% of commits` : "—" },
    ]);
    return s;
  }

  async function loadTimeline() {
    const g = el("granularity").value;
    const top = el("top").value;
    const data = await api(`${base}/timeline${rangeQuery({ granularity: g, top })}`);
    const canvas = el("timeline");
    if (!data.labels.length) {
      if (chart) { chart.destroy(); chart = null; }
      canvas.getContext("2d").clearRect(0, 0, canvas.width, canvas.height);
      canvas.parentElement.setAttribute("data-empty", "No commits in this range");
      return;
    }
    canvas.parentElement.removeAttribute("data-empty");
    chart = DCV.timelineChart(canvas, data, chart);
  }

  async function loadBoard() {
    const rows = await api(`${base}/contributors${rangeQuery({ sort })}`);
    document.querySelectorAll("#board th.sortable").forEach((th) =>
      th.classList.toggle("sorted", th.dataset.sort === sort));
    const body = document.querySelector("#board tbody");
    if (!rows.length) {
      body.innerHTML = `<tr><td colspan="7" class="empty">No commits in this range</td></tr>`;
      return;
    }
    body.innerHTML = rows.map((r) => `
      <tr class="clickable" data-id="${r.contributor_id}" tabindex="0">
        <td><div class="who"><span class="dot" style="background:${colorFor(r.color_index)}"></span>
          <div><div class="name">${esc(r.name)}</div><div class="email">${esc(r.email)}</div></div></div></td>
        <td class="num">${fmt(r.commits)}</td>
        <td class="num plus">+${fmt(r.additions)}</td>
        <td class="num minus">−${fmt(r.deletions)}</td>
        <td class="num">${fmt(r.active_days)}</td>
        <td class="num">${esc(r.last_day)}</td>
        <td class="num"><div class="share"><span>${r.share}%</span>
          <span class="bar"><i style="width:${r.share}%;background:${colorFor(r.color_index)}"></i></span></div></td>
      </tr>`).join("");
  }

  async function loadHeatmap() {
    const data = await api(`${base}/heatmap${rangeQuery()}`);
    DCV.renderHeatmap(el("heatmap"), data);
    el("peak").textContent = DCV.peakText(data.peak);
  }

  function updateExportLink() {
    el("export-btn").href = `${base}/export.csv${rangeQuery()}`;
  }

  async function loadAll() {
    updateExportLink();
    try {
      await Promise.all([loadSummary(), loadTimeline(), loadBoard(), loadHeatmap()]);
    } catch (err) {
      toast(err.message, true);
    }
  }

  // ------------------------------------------------------------------ events
  document.querySelectorAll("#board th.sortable").forEach((th) =>
    th.addEventListener("click", () => { sort = th.dataset.sort; loadBoard().catch((e) => toast(e.message, true)); }));

  const openRow = (row) => { location.href = `/repos/${repoId}/contributors/${row.dataset.id}${rangeQuery()}`; };
  document.querySelector("#board tbody").addEventListener("click", (e) => {
    const row = e.target.closest("tr[data-id]");
    if (row) openRow(row);
  });
  document.querySelector("#board tbody").addEventListener("keydown", (e) => {
    const row = e.target.closest("tr[data-id]");
    if (row && e.key === "Enter") openRow(row);
  });

  el("granularity").addEventListener("change", () => loadTimeline().catch((e) => toast(e.message, true)));
  el("top").addEventListener("change", () => loadTimeline().catch((e) => toast(e.message, true)));

  el("refresh-btn").addEventListener("click", async () => {
    const btn = el("refresh-btn");
    btn.disabled = true;
    btn.textContent = "Refreshing…";
    try {
      const result = await api(`${base}/refresh`, { method: "POST" });
      toast(`${fmt(result.new_commits)} new commit${result.new_commits === 1 ? "" : "s"} imported`);
      await loadAll();
    } catch (err) {
      toast(err.message, true);
    } finally {
      btn.disabled = false;
      btn.textContent = "↻ Refresh";
    }
  });

  // anchor presets on the last commit of the whole history
  api(`${base}/summary`).then((all) => {
    DCV.buildFilters(el("filters"), all.last_day, loadAll);
    loadAll();
  }).catch((err) => toast(err.message, true));
})();
