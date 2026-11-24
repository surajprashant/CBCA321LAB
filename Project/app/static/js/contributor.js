/* Contributor drill-down page. */
(() => {
  const { api, esc, fmt, toast, colorFor, rangeQuery, initials } = DCV;
  const repoId = document.body.dataset.repoId;
  const cid = document.body.dataset.contributorId;
  const base = `/api/repos/${repoId}`;
  const el = (id) => document.getElementById(id);
  let chart = null;

  function syncLinks() {
    const q = rangeQuery();
    el("back-link").href = `/repos/${repoId}${q}`;
    el("repo-link").href = `/repos/${repoId}${q}`;
  }

  async function load() {
    syncLinks();
    let d;
    try {
      d = await api(`${base}/contributors/${cid}${rangeQuery()}`);
    } catch (err) {
      el("name").textContent = "Contributor not found";
      toast(err.message, true);
      return;
    }
    const color = colorFor(d.color_index);
    const person = d.contributor;
    document.title = `${person.name} · Contribution Visualizer`;
    el("crumb-name").textContent = person.name;
    el("avatar").textContent = initials(person.name);
    el("avatar").style.background = color;
    el("name").innerHTML = `${esc(person.name)}${d.rank ? `<span class="badge">#${d.rank} of ${d.of}</span>` : ""}`;
    el("email").textContent = person.email;

    const s = d.stats;
    DCV.renderKpis(el("kpis"), s ? [
      { label: "Commits", value: fmt(s.commits), note: `${s.share}% of the team's commits` },
      { label: "Lines added", html: `<span class="plus">+${fmt(s.additions)}</span>`, note: "" },
      { label: "Lines deleted", html: `<span class="minus">−${fmt(s.deletions)}</span>`, note: `net ${s.net_lines >= 0 ? "+" : ""}${fmt(s.net_lines)}` },
      { label: "Active days", value: fmt(s.active_days), note: `${(s.commits / Math.max(1, s.active_days)).toFixed(1)} commits per active day` },
      { label: "First commit", value: s.first_day, note: "in this range" },
      { label: "Latest commit", value: s.last_day, note: "in this range" },
    ] : [{ label: "Commits", value: 0, note: "No commits in the selected range" }]);

    // timeline (one series in the person's own colour)
    const canvas = el("timeline");
    if (d.timeline.labels.length) {
      canvas.parentElement.removeAttribute("data-empty");
      chart = DCV.timelineChart(canvas, d.timeline, chart);
    } else {
      if (chart) { chart.destroy(); chart = null; }
      canvas.parentElement.setAttribute("data-empty", "No commits in this range");
    }

    DCV.renderHeatmap(el("heatmap"), d.heatmap);
    el("peak").textContent = DCV.peakText(d.heatmap.peak);

    el("folders").innerHTML = d.top_folders.length ? d.top_folders.map((f) => `
      <div class="item">
        <div class="top"><span class="mono">${esc(f.folder)}${f.folder === "(root)" ? "" : "/"}</span><span>${f.share}% · ${fmt(f.lines)} lines</span></div>
        <div class="track"><i style="width:${f.share}%;background:${color}"></i></div>
      </div>`).join("") : `<div class="empty">No file changes</div>`;

    el("files").querySelector("tbody").innerHTML = d.top_files.length ? d.top_files.map((f) => `
      <tr>
        <td class="mono" title="${esc(f.path)}">${esc(f.path)}</td>
        <td class="num">${fmt(f.changes)}</td>
        <td class="num"><span class="plus">+${fmt(f.additions)}</span> <span class="minus">−${fmt(f.deletions)}</span></td>
        <td class="num">${f.ownership}%</td>
      </tr>`).join("") : `<tr><td colspan="4" class="empty">No file changes</td></tr>`;

    el("recent").innerHTML = d.recent_commits.length ? d.recent_commits.map((c) => `
      <li>
        <span class="sha mono" title="${esc(c.sha)}">${esc(c.sha.slice(0, 7))}</span>
        <span class="msg" title="${esc(c.message)}">${esc(c.message)} <span class="day">· ${esc(c.day)}</span></span>
        <span class="delta"><span class="plus">+${fmt(c.additions)}</span> <span class="minus">−${fmt(c.deletions)}</span> · ${c.files_changed} file${c.files_changed === 1 ? "" : "s"}</span>
      </li>`).join("") : `<li class="empty" style="display:block">No commits in this range</li>`;
  }

  api(`${base}/summary`).then((all) => {
    DCV.buildFilters(el("filters"), all.last_day, load);
    load();
  }).catch((err) => toast(err.message, true));
})();
