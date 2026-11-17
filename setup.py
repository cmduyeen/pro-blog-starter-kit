#!/usr/bin/env python3
"""Zero-dependency CLI to scaffold a personal blog for GitHub Pages from modular themes and plugins."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent
THEMES_DIR = ROOT_DIR / "themes"
PLUGINS_DIR = ROOT_DIR / "plugins"
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")


def load_json(path: Path) -> dict[str, Any]:
    """Load and parse a JSON manifest file."""
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Manifest must be a JSON object: {path}")
    return data


def _is_safe_filename(name: str) -> bool:
    """Verify a manifest filename is a simple basename without path traversal."""
    return bool(name) and Path(name).name == name and ".." not in name


def discover_themes(themes_dir: Path = THEMES_DIR) -> dict[str, dict[str, Any]]:
    """Discover all blog themes in themes/<id>/theme.json."""
    themes: dict[str, dict[str, Any]] = {}
    if not themes_dir.exists():
        return themes
    for item in sorted(themes_dir.iterdir()):
        if not item.is_dir():
            continue
        manifest_path = item / "theme.json"
        if manifest_path.exists():
            data = load_json(manifest_path)
            themes[item.name] = {**data, "_dir": item}
    return themes


def discover_plugins(plugins_dir: Path = PLUGINS_DIR) -> dict[str, dict[str, Any]]:
    """Discover all blog plugins in plugins/<id>/plugin.json."""
    plugins: dict[str, dict[str, Any]] = {}
    if not plugins_dir.exists():
        return plugins
    for item in sorted(plugins_dir.iterdir()):
        if not item.is_dir():
            continue
        manifest_path = item / "plugin.json"
        if manifest_path.exists():
            data = load_json(manifest_path)
            plugins[item.name] = {**data, "_dir": item}
    return plugins


def validate_extensions(
    themes_dir: Path = THEMES_DIR,
    plugins_dir: Path = PLUGINS_DIR,
) -> list[str]:
    """Validate all theme and plugin manifests, templates, and workflows."""
    errors: list[str] = []

    if not themes_dir.exists():
        errors.append(f"Missing themes directory: {themes_dir}")
    else:
        for item in sorted(themes_dir.iterdir()):
            if not item.is_dir():
                continue
            manifest = item / "theme.json"
            if not manifest.exists():
                errors.append(f"Theme '{item.name}' is missing theme.json")
                continue
            try:
                data = load_json(manifest)
            except Exception as exc:
                errors.append(f"Theme '{item.name}' invalid JSON: {exc}")
                continue
            for key in ("id", "name", "engine", "config_file", "description", "author"):
                if not data.get(key):
                    errors.append(f"Theme '{item.name}' theme.json missing '{key}'")
            cfg_file = str(data.get("config_file", ""))
            if cfg_file and not _is_safe_filename(cfg_file):
                errors.append(f"Theme '{item.name}' has unsafe config_file '{cfg_file}'")
            cfg_tpl = item / "config.template"
            wf_file = item / "workflow.yml"
            if not cfg_tpl.exists():
                errors.append(f"Theme '{item.name}' is missing config.template")
            if not wf_file.exists():
                errors.append(f"Theme '{item.name}' is missing workflow.yml")
            else:
                wf_text = wf_file.read_text(encoding="utf-8")
                for req in ("name:", "on:", "jobs:"):
                    if req not in wf_text:
                        errors.append(f"Theme '{item.name}' workflow.yml missing '{req}'")

    if not plugins_dir.exists():
        errors.append(f"Missing plugins directory: {plugins_dir}")
    else:
        for item in sorted(plugins_dir.iterdir()):
            if not item.is_dir():
                continue
            manifest = item / "plugin.json"
            snippet = item / "snippet.md"
            if not manifest.exists():
                errors.append(f"Plugin '{item.name}' is missing plugin.json")
                continue
            try:
                data = load_json(manifest)
            except Exception as exc:
                errors.append(f"Plugin '{item.name}' invalid JSON: {exc}")
                continue
            for key in ("id", "name", "description", "author"):
                if not data.get(key):
                    errors.append(f"Plugin '{item.name}' plugin.json missing '{key}'")
            if not snippet.exists():
                errors.append(f"Plugin '{item.name}' is missing snippet.md")

    return errors


def parse_vars(raw_vars: list[str]) -> dict[str, str]:
    """Parse KEY=VALUE pairs from --var arguments safely."""
    parsed: dict[str, str] = {}
    for entry in raw_vars:
        if "=" not in entry:
            raise ValueError(f"Invalid --var '{entry}'. Expected KEY=VALUE format.")
        key, value = entry.split("=", 1)
        key = key.strip()
        val = value.strip()
        if not key:
            raise ValueError(f"Empty key in --var '{entry}'.")
        if "\n" in val or "\r" in val:
            raise ValueError(f"Invalid newline character in --var '{key}'.")
        parsed[key] = val
    return parsed


def render_placeholders(text: str, variables: dict[str, str]) -> str:
    """Replace {{KEY}} placeholders using provided variables (supports nested {{USERNAME}})."""
    rendered = text
    for _ in range(2):
        for key, value in variables.items():
            rendered = rendered.replace(f"{{{{{key}}}}}", value)
    return rendered


def compose_blog(
    *,
    username: str,
    blog_title: str,
    theme_id: str,
    plugin_ids: list[str],
    variables: dict[str, str],
    themes_dir: Path = THEMES_DIR,
    plugins_dir: Path = PLUGINS_DIR,
) -> dict[str, Any]:
    """Generate blog config file, deploy workflow, sample post, and plugin extras."""
    if not USERNAME_PATTERN.match(username):
        raise ValueError(f"Invalid GitHub username '{username}'.")

    themes = discover_themes(themes_dir)
    if theme_id not in themes:
        available = ", ".join(themes.keys()) or "(none)"
        raise ValueError(f"Unknown theme '{theme_id}'. Available: {available}")

    plugins = discover_plugins(plugins_dir)
    for pid in plugin_ids:
        if pid not in plugins:
            available = ", ".join(plugins.keys()) or "(none)"
            raise ValueError(f"Unknown plugin '{pid}'. Available: {available}")

    theme_data = themes[theme_id]
    theme_dir: Path = theme_data["_dir"]
    engine = str(theme_data.get("engine", "hugo"))

    merged_vars: dict[str, str] = {
        "USERNAME": username,
        "BLOG_TITLE": blog_title.strip() or f"{username}'s Blog",
        "BASE_URL": f"https://{username}.github.io/",
    }
    for k, v in (theme_data.get("defaults") or {}).items():
        merged_vars[str(k)] = str(v)
    for pid in plugin_ids:
        for k, v in (plugins[pid].get("defaults") or {}).items():
            merged_vars.setdefault(str(k), str(v))
    merged_vars.update(variables)

    config_raw = (theme_dir / "config.template").read_text(encoding="utf-8")
    plugin_config_blocks: list[str] = []
    extra_files: list[tuple[str, str]] = []

    for pid in plugin_ids:
        pdir: Path = plugins[pid]["_dir"]
        cfg_snip_path = pdir / f"config.{engine}.snippet"
        if cfg_snip_path.exists():
            plugin_config_blocks.append(
                render_placeholders(cfg_snip_path.read_text(encoding="utf-8").strip(), merged_vars)
            )
        extra_dir = pdir / "files"
        if extra_dir.exists():
            for f in sorted(extra_dir.rglob("*")):
                if f.is_file():
                    rel = f.relative_to(extra_dir).as_posix()
                    extra_files.append((rel, render_placeholders(f.read_text(encoding="utf-8"), merged_vars)))

    config_text = config_raw.replace("{{PLUGIN_CONFIG}}", "\n\n".join(plugin_config_blocks))
    config_text = render_placeholders(config_text, merged_vars).strip() + "\n"

    workflow_text = render_placeholders(
        (theme_dir / "workflow.yml").read_text(encoding="utf-8"),
        merged_vars,
    )

    if engine == "hugo":
        post_path = "content/posts/hello-world.md"
        post_content = (
            "---\n"
            f'title: "Welcome to {merged_vars["BLOG_TITLE"]}"\n'
            "date: 2026-11-17T09:00:00+07:00\n"
            "draft: false\n"
            'tags: ["welcome", "github-pages"]\n'
            "---\n\n"
            "Your personal blog on GitHub Pages is live! Edit or delete this post in `content/posts/`.\n"
        )
    else:
        post_path = "_posts/2026-11-17-hello-world.md"
        post_content = (
            "---\n"
            "layout: post\n"
            f'title: "Welcome to {merged_vars["BLOG_TITLE"]}"\n'
            "date: 2026-11-17 09:00:00 +0700\n"
            "tags: [welcome, github-pages]\n"
            "---\n\n"
            "Your personal blog on GitHub Pages is live! Edit or delete this post in `_posts/`.\n"
        )

    return {
        "config_file": str(theme_data["config_file"]),
        "config_content": config_text,
        "workflow_file": "deploy-blog.yml",
        "workflow_content": workflow_text,
        "post_path": post_path,
        "post_content": post_content,
        "extra_files": extra_files,
    }


def _replace_marker_block(text: str, marker: str, body: str) -> str:
    start_tag = f"<!-- {marker}:START -->"
    end_tag = f"<!-- {marker}:END -->"
    pattern = re.compile(re.escape(start_tag) + r".*?" + re.escape(end_tag), re.DOTALL)
    if not pattern.search(text):
        raise ValueError(f"Missing {start_tag} / {end_tag} markers in README.md")
    replacement = f"{start_tag}\n{body.strip()}\n{end_tag}"
    return pattern.sub(lambda _: replacement, text, count=1)


def _render_grid_cells(cells: list[str], columns: int = 2) -> str:
    rows: list[str] = ["<table>"]
    width_pct = int(100 / columns)
    for idx in range(0, len(cells), columns):
        rows.append("  <tr>")
        chunk = cells[idx : idx + columns]
        for cell in chunk:
            rows.append(f'    <td align="center" valign="top" width="{width_pct}%">\n{cell}\n    </td>')
        for _ in range(columns - len(chunk)):
            rows.append(f'    <td width="{width_pct}%"></td>')
        rows.append("  </tr>")
    rows.append("</table>")
    return "\n".join(rows)


def render_themes_table(themes_dir: Path = THEMES_DIR, root_dir: Path = ROOT_DIR) -> str:
    themes = discover_themes(themes_dir)
    cells: list[str] = []
    for tid, data in themes.items():
        tdir: Path = data["_dir"]
        preview_md = f"themes/{tid}/PREVIEW.md" if (tdir / "PREVIEW.md").exists() else f"themes/{tid}/config.template"
        img_rel = ""
        if (tdir / "preview.svg").exists():
            img_rel = f"themes/{tid}/preview.svg"
        elif (root_dir / "assets" / "previews" / f"{tid}.svg").exists():
            img_rel = f"assets/previews/{tid}.svg"
        name = data.get("name", tid)
        engine = str(data.get("engine", "hugo")).upper()
        author = str(data.get("author", "community"))
        desc = str(data.get("description", ""))
        img_tag = f'      <a href="{preview_md}"><img src="{img_rel}" width="280" alt="{name} Preview"/></a><br/>\n' if img_rel else ""
        cells.append(
            f"{img_tag}"
            f'      <b><code>{tid}</code></b> ({engine}) · <a href="{preview_md}">Preview</a> · <a href="themes/{tid}/config.template">Config</a><br/>\n'
            f"      <sub>{desc} <i>(by @{author})</i></sub>"
        )
    return _render_grid_cells(cells, columns=2)


def render_plugins_table(plugins_dir: Path = PLUGINS_DIR, root_dir: Path = ROOT_DIR) -> str:
    plugins = discover_plugins(plugins_dir)
    cells: list[str] = []
    for pid, data in plugins.items():
        pdir: Path = data["_dir"]
        preview_md = f"plugins/{pid}/PREVIEW.md" if (pdir / "PREVIEW.md").exists() else f"plugins/{pid}/snippet.md"
        img_rel = ""
        if (pdir / "preview.svg").exists():
            img_rel = f"plugins/{pid}/preview.svg"
        elif (root_dir / "assets" / "previews" / "plugins" / f"{pid}.svg").exists():
            img_rel = f"assets/previews/plugins/{pid}.svg"
        name = data.get("name", pid)
        author = str(data.get("author", "community"))
        desc = str(data.get("description", ""))
        img_tag = f'      <a href="{preview_md}"><img src="{img_rel}" width="240" alt="{name} Preview"/></a><br/>\n' if img_rel else ""
        cells.append(
            f"{img_tag}"
            f'      <b><code>{pid}</code></b> · <a href="{preview_md}">Guide</a> · <a href="plugins/{pid}/snippet.md">Snippet</a><br/>\n'
            f"      <sub>{desc} <i>(by @{author})</i></sub>"
        )
    return _render_grid_cells(cells, columns=3)


def build_catalog_data(themes_dir: Path = THEMES_DIR, plugins_dir: Path = PLUGINS_DIR) -> dict[str, Any]:
    themes_raw = discover_themes(themes_dir)
    plugins_raw = discover_plugins(plugins_dir)

    themes_out: list[dict[str, Any]] = []
    for tid, data in themes_raw.items():
        tdir: Path = data["_dir"]
        themes_out.append(
            {
                "id": tid,
                "name": data.get("name", tid),
                "engine": data.get("engine", "hugo"),
                "config_file": data.get("config_file", "hugo.toml"),
                "description": data.get("description", ""),
                "author": data.get("author", "community"),
                "defaults": data.get("defaults", {}),
                "config_template": (tdir / "config.template").read_text(encoding="utf-8"),
                "workflow_content": (tdir / "workflow.yml").read_text(encoding="utf-8"),
            }
        )

    plugins_out: list[dict[str, Any]] = []
    for pid, data in plugins_raw.items():
        pdir: Path = data["_dir"]
        snippets: dict[str, str] = {}
        for eng in ("hugo", "jekyll"):
            sp = pdir / f"config.{eng}.snippet"
            if sp.exists():
                snippets[eng] = sp.read_text(encoding="utf-8").strip()
        plugins_out.append(
            {
                "id": pid,
                "name": data.get("name", pid),
                "description": data.get("description", ""),
                "author": data.get("author", "community"),
                "defaults": data.get("defaults", {}),
                "config_snippets": snippets,
                "snippet": (pdir / "snippet.md").read_text(encoding="utf-8").strip(),
            }
        )

    return {"themes": themes_out, "plugins": plugins_out}


def sync_readme_catalog(
    readme_path: Path | None = None,
    themes_dir: Path = THEMES_DIR,
    plugins_dir: Path = PLUGINS_DIR,
    catalog_path: Path | None = None,
) -> bool:
    target = readme_path or (ROOT_DIR / "README.md")
    original = target.read_text(encoding="utf-8")
    updated = _replace_marker_block(original, "THEMES-TABLE", render_themes_table(themes_dir, target.parent))
    updated = _replace_marker_block(updated, "PLUGINS-TABLE", render_plugins_table(plugins_dir, target.parent))
    changed = updated != original
    if changed:
        target.write_text(updated, encoding="utf-8")

    cat_target = catalog_path or (target.parent / "docs" / "catalog.json")
    if cat_target.parent.exists():
        new_cat = json.dumps(build_catalog_data(themes_dir, plugins_dir), indent=2, ensure_ascii=False) + "\n"
        old_cat = cat_target.read_text(encoding="utf-8") if cat_target.exists() else ""
        if new_cat != old_cat:
            cat_target.write_text(new_cat, encoding="utf-8")
            changed = True

    return changed


def list_catalog(themes_dir: Path = THEMES_DIR, plugins_dir: Path = PLUGINS_DIR) -> None:
    themes = discover_themes(themes_dir)
    plugins = discover_plugins(plugins_dir)
    print("Available Blog Themes:")
    for tid, data in themes.items():
        print(f"  - {tid} [{data.get('engine')}]: {data.get('name')} — {data.get('description')}")
    print("\nAvailable Blog Plugins:")
    for pid, data in plugins.items():
        print(f"  - {pid}: {data.get('name')} — {data.get('description')}")


def interactive_wizard(
    themes_dir: Path = THEMES_DIR,
    plugins_dir: Path = PLUGINS_DIR,
) -> tuple[str, str, str, list[str], dict[str, str]]:
    themes = discover_themes(themes_dir)
    plugins = discover_plugins(plugins_dir)
    theme_ids = list(themes.keys())
    plugin_ids_all = list(plugins.keys())

    print("=== Pro Blog Starter Kit — Interactive Setup ===\n")
    username = input("1. Enter your GitHub username: ").strip()
    if not USERNAME_PATTERN.match(username):
        raise ValueError(f"Invalid GitHub username '{username}'.")
    blog_title = input(f"2. Blog title (Enter for '{username}'s Blog'): ").strip() or f"{username}'s Blog"

    print("\n3. Choose a Blog Theme:")
    for idx, tid in enumerate(theme_ids, start=1):
        print(f"  [{idx}] {tid} ({themes[tid].get('engine')}) — {themes[tid].get('description')}")
    raw_theme = input(f"Enter number [1-{len(theme_ids)}] (default 1): ").strip()
    theme_idx = int(raw_theme) - 1 if raw_theme else 0
    if not (0 <= theme_idx < len(theme_ids)):
        raise ValueError("Theme selection out of range.")
    chosen_theme = theme_ids[theme_idx]

    print("\n4. Choose Plugins (comma-separated numbers, or Enter for none):")
    for idx, pid in enumerate(plugin_ids_all, start=1):
        print(f"  [{idx}] {pid} — {plugins[pid].get('description')}")
    raw_plugins = input("Plugins (e.g. 1,3,5): ").strip()
    chosen_plugins: list[str] = []
    if raw_plugins:
        for token in raw_plugins.split(","):
            token = token.strip()
            if not token:
                continue
            p_idx = int(token) - 1
            if not (0 <= p_idx < len(plugin_ids_all)):
                raise ValueError(f"Plugin selection '{token}' out of range.")
            pid = plugin_ids_all[p_idx]
            if pid not in chosen_plugins:
                chosen_plugins.append(pid)

    return username, blog_title, chosen_theme, chosen_plugins, {}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scaffold a personal GitHub Pages blog from modular themes and plugins."
    )
    parser.add_argument("--list", action="store_true", help="List available blog themes and plugins.")
    parser.add_argument("--validate", action="store_true", help="Validate all theme and plugin manifests.")
    parser.add_argument("--sync-readme", action="store_true", help="Update README.md catalog and docs/catalog.json.")
    parser.add_argument("-i", "--interactive", action="store_true", help="Run guided interactive setup.")
    parser.add_argument("--username", help="Your GitHub username.")
    parser.add_argument("--title", default=None, help="Your blog title.")
    parser.add_argument("--theme", default="hugo-papermod", help="Theme ID (default: hugo-papermod).")
    parser.add_argument("--plugins", default="", help="Comma-separated plugin IDs.")
    parser.add_argument("--var", action="append", default=[], help="Custom KEY=VALUE variable.")
    parser.add_argument("--output-dir", default=".", help="Output directory (default: current directory).")
    parser.add_argument("--dry-run", action="store_true", help="Preview generated files without writing.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.validate:
        errors = validate_extensions()
        if errors:
            for err in errors:
                print(f"Error: {err}", file=sys.stderr)
            return 1
        print("All blog theme and plugin manifests are valid.")
        return 0

    if args.list:
        list_catalog()
        return 0

    if args.sync_readme:
        changed = sync_readme_catalog()
        print("Updated README.md and docs/catalog.json." if changed else "Catalog already up to date.")
        return 0

    try:
        if args.interactive or not args.username:
            username, blog_title, theme_id, plugin_ids, variables = interactive_wizard()
        else:
            username = args.username
            blog_title = args.title or f"{username}'s Blog"
            theme_id = args.theme
            plugin_ids = [p.strip() for p in args.plugins.split(",") if p.strip()]
            variables = parse_vars(args.var)

        bundle = compose_blog(
            username=username,
            blog_title=blog_title,
            theme_id=theme_id,
            plugin_ids=plugin_ids,
            variables=variables,
        )

        out_root = Path(args.output_dir).resolve()
        if args.dry_run:
            print(f"[dry-run] Would write {out_root / bundle['config_file']}")
            print(f"[dry-run] Would write {out_root / '.github' / 'workflows' / bundle['workflow_file']}")
            print(f"[dry-run] Would write {out_root / bundle['post_path']}")
            for rel, _ in bundle["extra_files"]:
                print(f"[dry-run] Would write {out_root / rel}")
            return 0

        out_root.mkdir(parents=True, exist_ok=True)
        (out_root / bundle["config_file"]).write_text(bundle["config_content"], encoding="utf-8")
        wf_dir = out_root / ".github" / "workflows"
        wf_dir.mkdir(parents=True, exist_ok=True)
        (wf_dir / bundle["workflow_file"]).write_text(bundle["workflow_content"], encoding="utf-8")
        post_target = out_root / bundle["post_path"]
        post_target.parent.mkdir(parents=True, exist_ok=True)
        post_target.write_text(bundle["post_content"], encoding="utf-8")

        for rel, content in bundle["extra_files"]:
            target = out_root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

        print(f"Scaffolded blog into {out_root}")
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
