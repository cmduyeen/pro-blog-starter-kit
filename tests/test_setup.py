import tempfile
import unittest
from pathlib import Path

import setup


class TestBlogStarterKit(unittest.TestCase):
    def test_validate_extensions_passes(self) -> None:
        self.assertEqual(setup.validate_extensions(), [])

    def test_discover_themes_and_plugins(self) -> None:
        themes = setup.discover_themes()
        plugins = setup.discover_plugins()
        for tid in ("hugo-papermod", "hugo-minimal-notes", "jekyll-chirpy", "jekyll-minima"):
            self.assertIn(tid, themes)
        for pid in (
            "giscus-comments",
            "seo-geo-pack",
            "obsidian-template",
            "rss-profile-sync",
            "math-diagrams",
            "goatcounter-analytics",
        ):
            self.assertIn(pid, plugins)

    def test_compose_hugo_blog_replaces_placeholders(self) -> None:
        bundle = setup.compose_blog(
            username="octocat",
            blog_title="Octocat Notes",
            theme_id="hugo-papermod",
            plugin_ids=["giscus-comments", "seo-geo-pack", "rss-profile-sync"],
            variables={},
        )
        self.assertEqual(bundle["config_file"], "hugo.toml")
        self.assertIn('title = "Octocat Notes"', bundle["config_content"])
        self.assertIn("octocat/octocat.github.io", bundle["config_content"])
        self.assertNotIn("{{", bundle["config_content"])
        extra_paths = [p for p, _ in bundle["extra_files"]]
        self.assertIn("static/robots.txt", extra_paths)
        self.assertIn("static/llms.txt", extra_paths)

    def test_cli_scaffolds_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rc = setup.main(
                [
                    "--username",
                    "octocat",
                    "--title",
                    "Octocat Blog",
                    "--theme",
                    "jekyll-minima",
                    "--plugins",
                    "giscus-comments",
                    "--output-dir",
                    tmp,
                ]
            )
            self.assertEqual(rc, 0)
            out = Path(tmp)
            self.assertTrue((out / "_config.yml").exists())
            self.assertTrue((out / ".github" / "workflows" / "deploy-blog.yml").exists())
            self.assertTrue((out / "_posts" / "2026-11-17-hello-world.md").exists())

    def test_parse_vars_rejects_newlines(self) -> None:
        with self.assertRaises(ValueError):
            setup.parse_vars(["GOATCOUNTER_CODE=abc\nmalicious=1"])


if __name__ == "__main__":
    unittest.main()
