import subprocess

import pytest

from scripts.stamp_release import stamp_release


def git(cwd, *args):
    return subprocess.check_output(["git", "-C", str(cwd), *args], text=True).strip()


@pytest.fixture
def repository(tmp_path, monkeypatch):
    git(tmp_path, "init", "-b", "main")
    git(tmp_path, "config", "user.name", "Test")
    git(tmp_path, "config", "user.email", "test@example.com")
    constants = tmp_path / "app/core/constants.py"
    constants.parent.mkdir(parents=True)
    constants.write_text('APP_VERSION = "1.0.0"\nOTHER = "preserve"\n', encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "initial")
    git(tmp_path, "tag", "v1.2.3")
    git(tmp_path, "checkout", "--detach", "v1.2.3")
    monkeypatch.chdir(tmp_path)
    return tmp_path, constants


def test_stamp_only_changes_workspace_and_reruns_safely(repository):
    repo, constants = repository
    refs = git(repo, "show-ref")
    before = git(repo, "rev-parse", "HEAD")
    committed = git(repo, "show", "HEAD:app/core/constants.py")
    assert stamp_release("v1.2.3") == "1.2.3"
    assert constants.read_text() == 'APP_VERSION = "1.2.3"\nOTHER = "preserve"\n'
    assert git(repo, "rev-parse", "HEAD") == before
    assert git(repo, "show-ref") == refs
    assert git(repo, "show", "HEAD:app/core/constants.py") == committed
    assert git(repo, "diff", "--name-only") == "app/core/constants.py"
    assert git(repo, "diff", "--cached", "--name-only") == ""
    assert stamp_release("v1.2.3") == "1.2.3"
    assert git(repo, "show-ref") == refs


@pytest.mark.parametrize("tag", ["1.2.3", "v1.2.3-rc.1", "v01.2.3", "v65536.0.0", "v1.2", "v1.2.3;evil"])
def test_invalid_tags_do_not_change_file(repository, tag):
    _, constants = repository
    original = constants.read_bytes()
    with pytest.raises(ValueError):
        stamp_release(tag)
    assert constants.read_bytes() == original


def test_matching_version_keeps_checkout_clean(repository):
    repo, _ = repository
    assert stamp_release("v1.0.0") == "1.0.0"
    assert git(repo, "status", "--porcelain") == ""


@pytest.mark.parametrize("content", ['OTHER = "keep"\n', 'APP_VERSION = "1.0.0"\nAPP_VERSION = "2.0.0"\n'])
def test_missing_or_duplicate_assignment_does_not_change_file(repository, content):
    _, constants = repository
    constants.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError, match="one APP_VERSION"):
        stamp_release("v1.2.3")
    assert constants.read_text() == content
