# Contributing Blog Themes & Plugins

`pro-blog-starter-kit` uses an extensible **Theme + Plugin** architecture. Anyone can add a new Hugo/Jekyll theme or blog plugin via Pull Request without modifying `setup.py`.

## Add a Theme (`themes/<theme-id>/`)

1. `theme.json` with `id`, `name`, `engine` (`hugo` or `jekyll`), `config_file` (`hugo.toml` or `_config.yml`), `description`, `author`.
2. `config.template` with `{{BLOG_TITLE}}`, `{{BASE_URL}}`, `{{USERNAME}}`, and `{{PLUGIN_CONFIG}}`.
3. `workflow.yml` for GitHub Pages deployment.
4. Optional `preview.svg` (`320×180`).

## Add a Plugin (`plugins/<plugin-id>/`)

1. `plugin.json` with `id`, `name`, `description`, `author`.
2. `snippet.md` explaining the plugin.
3. Optional `config.hugo.snippet`, `config.jekyll.snippet`, `files/`, and `preview.svg` (`320×140`).

## Validate Locally

```bash
python setup.py --validate
python -m unittest discover -s tests -v
```
