import pytest

from app.services.job_import import normalize_remotive_job
from app.services.job_normalization import html_to_text, infer_seniority
from app.services.job_scoring import calculate_match_score
from app.services.python_org_import import parse_python_org_jobs


@pytest.mark.parametrize("title, expected", [
    ("Junior Developer", "junior"), ("JR. Engineer", "junior"),
    ("Entry level Engineer", "junior"), ("ENTRY-LEVEL Engineer", "junior"),
    ("Senior Developer", "senior"), ("sR. Engineer", "senior"),
    ("Tech Lead", "lead"), ("Team Lead", "lead"), ("Lead Developer", "lead"),
    ("Senior Staff Engineer", "staff"), ("Principal Engineer", "principal"),
    ("Engineering Intern", "intern"), ("Summer Internship", "intern"),
    ("Developer", "unknown"), ("International Staffing Leadership", "unknown"),
    ("Senior Tech Lead", "lead"),
])
def test_seniority(title: str, expected: str) -> None:
    assert infer_seniority(title) == expected


def test_html_cleaning_and_remotive_normalization() -> None:
    html = ('<style>.python {color:red}</style><script>aws()</script>'
            '<p style="color:red">Build <strong>APIs</strong> &amp; tools.</p>'
            '<ul><li>Write tests</li><li>Review code</li></ul>'
            '<img src="https://tracker.example/python" alt="python">')
    expected = "Build APIs & tools.\nWrite tests\nReview code"
    assert html_to_text(html) == expected
    job = normalize_remotive_job(dict(title="Sr. Developer", company_name="Example",
        candidate_required_location="Remote", url="https://example.com/1", description=html))
    assert job is not None
    assert job.description == expected
    assert "<" not in job.description and "tracker" not in job.description
    assert job.seniority == "senior"


def test_python_org_has_no_provider_python_points() -> None:
    html = '''<ol class="list-recent-jobs"><li>
    <span class="listing-company-name"><a href="/jobs/123/">Junior Accountant</a><br>Example</span>
    <span class="listing-location">London</span>
    <span class="listing-job-type">Finance</span></li></ol>'''
    _, jobs = parse_python_org_jobs(html, "https://www.python.org/jobs/")
    job = jobs[0]
    assert job.description == "Finance"
    assert job.seniority == "junior"
    assert calculate_match_score(title=job.title, description=job.description,
        remote=job.remote, seniority=job.seniority) == 15


@pytest.mark.parametrize("description", [
    "Source: Python.org Job Board. Listing summary; full description: https://www.python.org/jobs/123/\nFinance",
    '<style>python fastapi</style><img alt="docker" src="https://aws.example/">Finance',
    'Source: Remotive\nFinance https://example.com/python www.python.org python.org',
])
def test_metadata_does_not_score(description: str) -> None:
    assert calculate_match_score(title="Accountant", description=description,
                                 remote=False, seniority="unknown") == 0


def test_real_anchor_text_still_scores() -> None:
    assert calculate_match_score(title="", description='<a href="https://example.com">Python</a>',
                                 remote=False, seniority="unknown") == 9
