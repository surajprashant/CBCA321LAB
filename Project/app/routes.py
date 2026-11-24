"""HTTP layer: page routes and the JSON REST API."""
from __future__ import annotations

from flask import Blueprint, Response, abort, current_app, jsonify, render_template, request

from .importer import ImportError_

pages = Blueprint("pages", __name__)
api = Blueprint("api", __name__, url_prefix="/api")


def _services():
    ext = current_app.extensions["dcv"]
    return ext["store"], ext["importer"], ext["analytics"]


def _repo_or_404(repo_id: int) -> dict:
    store, _, _ = _services()
    repo = store.get_repository(repo_id)
    if repo is None:
        abort(404, description="Repository not found")
    return repo


def _range() -> tuple[str | None, str | None]:
    return request.args.get("since") or None, request.args.get("until") or None


# --------------------------------------------------------------------------- #
# error handling: API errors are always JSON {"error": "..."}
# --------------------------------------------------------------------------- #
@api.errorhandler(400)
@api.errorhandler(404)
@api.errorhandler(405)
def _api_error(err):
    return jsonify({"error": err.description}), err.code


@api.errorhandler(ValueError)
def _bad_value(err):
    return jsonify({"error": str(err)}), 400


@api.errorhandler(ImportError_)
def _bad_import(err):
    return jsonify({"error": str(err)}), 400


# --------------------------------------------------------------------------- #
# pages
# --------------------------------------------------------------------------- #
@pages.get("/")
def home():
    return render_template("index.html")


@pages.get("/repos/<int:repo_id>")
def repo_page(repo_id: int):
    return render_template("repo.html", repo=_repo_or_404(repo_id))


@pages.get("/repos/<int:repo_id>/contributors/<int:contributor_id>")
def contributor_page(repo_id: int, contributor_id: int):
    return render_template("contributor.html", repo=_repo_or_404(repo_id),
                           contributor_id=contributor_id)


# --------------------------------------------------------------------------- #
# API: repositories
# --------------------------------------------------------------------------- #
@api.get("/repos")
def list_repos():
    store, _, _ = _services()
    return jsonify(store.list_repositories())


@api.post("/repos")
def create_repo():
    _, importer, _ = _services()
    body = request.get_json(silent=True) or {}
    source = body.get("source")
    if not isinstance(source, str) or not source.strip():
        abort(400, description="Field 'source' (local path or Git URL) is required")
    result = importer.import_source(source)
    return jsonify(result), (201 if result["created"] else 200)


@api.post("/repos/<int:repo_id>/refresh")
def refresh_repo(repo_id: int):
    _repo_or_404(repo_id)
    _, importer, _ = _services()
    return jsonify(importer.refresh(repo_id))


@api.delete("/repos/<int:repo_id>")
def delete_repo(repo_id: int):
    _repo_or_404(repo_id)
    _, importer, _ = _services()
    importer.delete(repo_id)
    return "", 204


@api.get("/repos/<int:repo_id>")
def get_repo(repo_id: int):
    return jsonify(_repo_or_404(repo_id))


# --------------------------------------------------------------------------- #
# API: analytics
# --------------------------------------------------------------------------- #
@api.get("/repos/<int:repo_id>/summary")
def summary(repo_id: int):
    _repo_or_404(repo_id)
    return jsonify(_services()[2].summary(repo_id, *_range()))


@api.get("/repos/<int:repo_id>/contributors")
def contributors(repo_id: int):
    _repo_or_404(repo_id)
    sort = request.args.get("sort", "commits")
    return jsonify(_services()[2].leaderboard(repo_id, *_range(), sort=sort))


@api.get("/repos/<int:repo_id>/timeline")
def timeline(repo_id: int):
    _repo_or_404(repo_id)
    try:
        top = int(request.args.get("top", 5))
    except ValueError:
        raise ValueError("'top' must be a whole number") from None
    granularity = request.args.get("granularity", "auto")
    return jsonify(_services()[2].timeline(repo_id, *_range(), granularity=granularity, top=top))


@api.get("/repos/<int:repo_id>/heatmap")
def heatmap(repo_id: int):
    _repo_or_404(repo_id)
    cid = request.args.get("contributor_id", type=int)
    return jsonify(_services()[2].heatmap(repo_id, cid, *_range()))


@api.get("/repos/<int:repo_id>/contributors/<int:contributor_id>")
def contributor_detail(repo_id: int, contributor_id: int):
    _repo_or_404(repo_id)
    detail = _services()[2].contributor_detail(repo_id, contributor_id, *_range())
    if detail is None:
        abort(404, description="Contributor not found in this repository")
    return jsonify(detail)


@api.get("/repos/<int:repo_id>/export.csv")
def export_csv(repo_id: int):
    repo = _repo_or_404(repo_id)
    csv_text = _services()[2].export_csv(repo_id, *_range())
    filename = f"{repo['name']}-contributors.csv".replace('"', "")
    return Response(csv_text, mimetype="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
