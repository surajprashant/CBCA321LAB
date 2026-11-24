/* Home page: import form + list of repositories. */
(() => {
  const { api, esc, fmt, toast } = DCV;
  const list = document.getElementById("repos");
  const form = document.getElementById("import-form");
  const button = document.getElementById("import-btn");

  const ago = (iso) => {
    const seconds = (Date.now() - new Date(iso).getTime()) / 1000;
    if (seconds < 60) return "just now";
    if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)} h ago`;
    return new Date(iso).toLocaleDateString();
  };

  async function load() {
    try {
      const repos = await api("/api/repos");
      if (!repos.length) {
        list.innerHTML = `<div class="card empty" style="grid-column:1/-1">No repositories yet. Import one above to get started.</div>`;
        return;
      }
      list.innerHTML = repos.map((r) => `
        <article class="card repo-card" data-id="${r.id}">
          <div>
            <h3><a href="/repos/${r.id}">${esc(r.name)}</a></h3>
            <div class="source">${esc(r.source)}</div>
          </div>
          <div class="meta">
            <span><b>${fmt(r.commit_count)}</b> commits</span>
            <span><b>${fmt(r.contributor_count)}</b> contributors</span>
            <span class="muted">updated ${ago(r.updated_at)}</span>
          </div>
          <div class="row">
            <a class="btn btn-sm btn-primary" href="/repos/${r.id}">Open dashboard</a>
            <button type="button" class="btn-sm" data-action="refresh">↻ Refresh</button>
            <button type="button" class="btn-sm btn-danger" data-action="delete">Remove</button>
          </div>
        </article>`).join("");
    } catch (err) {
      list.innerHTML = `<div class="card empty" style="grid-column:1/-1">${esc(err.message)}</div>`;
    }
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const source = document.getElementById("source").value.trim();
    if (!source) return;
    button.disabled = true;
    button.textContent = "Importing…";
    try {
      const result = await api("/api/repos", { method: "POST", body: JSON.stringify({ source }) });
      const repo = result.repository;
      toast(result.created
        ? `Imported ${repo.name}: ${fmt(repo.commit_count)} commits by ${fmt(repo.contributor_count)} people`
        : `${repo.name} already imported – ${fmt(result.new_commits)} new commits added`);
      setTimeout(() => { location.href = `/repos/${repo.id}`; }, 700);
    } catch (err) {
      toast(err.message, true);
    } finally {
      button.disabled = false;
      button.textContent = "Import repository";
    }
  });

  list.addEventListener("click", async (event) => {
    const btn = event.target.closest("button[data-action]");
    if (!btn) return;
    const card = btn.closest(".repo-card");
    const id = card.dataset.id;
    const name = card.querySelector("h3").textContent;
    btn.disabled = true;
    try {
      if (btn.dataset.action === "refresh") {
        const result = await api(`/api/repos/${id}/refresh`, { method: "POST" });
        toast(`${name}: ${fmt(result.new_commits)} new commit${result.new_commits === 1 ? "" : "s"}`);
      } else {
        if (!confirm(`Remove "${name}" from the visualizer? (The repository on disk is not touched.)`)) return;
        await api(`/api/repos/${id}`, { method: "DELETE" });
        toast(`Removed ${name}`);
      }
      await load();
    } catch (err) {
      toast(err.message, true);
    } finally {
      btn.disabled = false;
    }
  });

  load();
})();
