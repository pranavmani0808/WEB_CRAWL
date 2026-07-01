import pytest
from bs4 import BeautifulSoup
from app.crawler.rate_limiter import RateLimiter
from app.crawler.seo_extractor import SEOExtractor
from app.crawler.issue_detector import IssueDetector

def test_rate_limiter():
    limiter = RateLimiter(requests_per_second=100.0)
    assert limiter.requests_per_second == 100.0
    assert limiter.min_interval == 0.01

def test_seo_extractor_basic():
    html = """
    <html>
        <head>
            <title>Test Page Title</title>
            <meta name="description" content="This is a test meta description.">
            <link rel="canonical" href="https://example.com/test">
        </head>
        <body>
            <h1>Main Heading</h1>
            <h2>Sub Heading 1</h2>
            <h2>Sub Heading 2</h2>
            <p>Word count test paragraph with some random words to count.</p>
            <img src="/img1.png" alt="Image 1">
            <a href="/internal-link">Internal Link</a>
            <a href="https://other.com/external">External Link</a>
        </body>
    </html>
    """
    
    result, soup = SEOExtractor.extract_all(html, "https://example.com/test", "example.com")
    
    assert result['title'] == "Test Page Title"
    assert result['meta_description'] == "This is a test meta description."
    assert result['h1'] == "Main Heading"
    assert len(result['h2']) == 2
    assert result['h2'][0] == "Sub Heading 1"
    assert result['canonical_url'] == "https://example.com/test"
    assert result['word_count'] > 0
    assert len(result['images']) == 1
    assert result['images'][0]['src'] == "https://example.com/img1.png"
    assert result['images'][0]['alt'] == "Image 1"
    assert result['internal_links'] == 1
    assert result['external_links'] == 1

def test_issue_detector():
    detector = IssueDetector()
    
    # Page with issues: missing title, description, and h1
    bad_result = {
        'url': 'https://example.com/bad',
        'title': '',
        'meta_description': '',
        'h1': '',
        'word_count': 50,
        'status_code': 200,
        'viewport': '',
        'lang': '',
        'images': [{'src': '/img.png', 'alt': ''}]
    }
    
    issues = detector.detect_issues(bad_result)
    
    issue_names = [i['issue'] for i in issues]
    assert "Missing Title Tag" in issue_names
    assert "Missing Meta Description" in issue_names
    assert "Missing H1 Tag" in issue_names
    assert "Thin Content" in issue_names
    assert "Missing Viewport Meta Tag" in issue_names
    assert "Missing Language Attribute" in issue_names
    assert "Images Without Alt Text" in issue_names
