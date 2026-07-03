import time

from app.crawler.issue_detector import IssueDetector


def _page(url, title, desc, h1, wc=450):
    return {"url": url, "title": title, "meta_description": desc, "h1": h1, "word_count": wc}


def test_duplication_detects_planted_near_duplicate():
    pages = [
        _page("https://a.com/1", "Unique First Page Title Here", "A completely distinct description of the first page.", "First"),
        _page("https://a.com/2", "Identical Title For Both Pages", "Same description text shared by both pages exactly.", "Dup"),
        _page("https://a.com/3", "Identical Title For Both Pages", "Same description text shared by both pages exactly.", "Dup"),
        _page("https://a.com/4", "Another Unrelated Page Title!!", "Totally different content that matches nothing else.", "Other"),
    ]
    issues = IssueDetector().detect_duplication_issues(pages)
    assert len(issues) == 1
    assert issues[0]["url"] == "https://a.com/3"
    assert "https://a.com/2" in issues[0]["details"]


def test_duplication_groups_template_sites_instead_of_exploding():
    """Regression test: template-heavy catalogs (every page >85% similar to
    every other) used to produce O(n^2) issue records - 1.4M for a 1200-page
    site - and take minutes of CPU. Pages must be flagged at most once, and
    the whole scan must stay fast.
    """
    pages = [
        _page(
            f"https://shop.com/item{i}",
            f"Buy Widget Model {i:04d} Online - Best Prices | MegaShop",
            f"Shop Widget Model {i:04d} at MegaShop. Free shipping on orders over $50.",
            f"Widget Model {i:04d}",
        )
        for i in range(500)
    ]
    start = time.time()
    issues = IssueDetector().detect_duplication_issues(pages)
    elapsed = time.time() - start

    # Every page after the first is a duplicate of the first - exactly once each.
    assert len(issues) == 499
    assert len({i["url"] for i in issues}) == 499
    assert elapsed < 5


def test_duplication_ignores_dissimilar_pages():
    pages = [
        _page("https://a.com/x", "Short title", "First description entirely about cats and their habits.", "Cats", 200),
        _page("https://a.com/y", "A very much longer and different page title string", "Second description entirely about deep sea welding rigs.", "Welding", 900),
    ]
    assert IssueDetector().detect_duplication_issues(pages) == []
