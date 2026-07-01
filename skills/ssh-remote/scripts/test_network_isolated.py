# Tests for network_isolated internal-mirror whitelist.
from ssh_ops import (
    _is_internal_host,
    _extract_urls,
    _extract_host_from_url,
    _command_needs_public_network,
)


# --- _is_internal_host --- #

def test_is_internal_rfc1918_ipv4():
    assert _is_internal_host("10.0.0.1")
    assert _is_internal_host("172.16.5.10")
    assert _is_internal_host("192.168.1.100")


def test_is_internal_loopback():
    assert _is_internal_host("127.0.0.1")
    assert _is_internal_host("localhost")
    assert _is_internal_host("0.0.0.0")


def test_is_internal_suffix():
    assert _is_internal_host("repo.corp")
    assert _is_internal_host("pypi.internal")
    assert _is_internal_host("artifacts.lan")
    assert _is_internal_host("npm.intranet")
    assert _is_internal_host("Pypi.INTERNAL")  # case-insensitive


def test_is_internal_public_domain():
    assert not _is_internal_host("pypi.org")
    assert not _is_internal_host("github.com")
    assert not _is_internal_host("8.8.8.8")


def test_is_internal_edge_cases():
    assert not _is_internal_host("")
    assert not _is_internal_host("not-a-host")
    # URL with userinfo/port
    assert _is_internal_host("user@10.0.0.1:8080")
    assert not _is_internal_host("user@pypi.org:443")


# --- _extract_urls --- #

def test_extract_urls_basic():
    assert _extract_urls("curl http://10.0.0.5:8080/x") == ["http://10.0.0.5:8080/x"]
    assert _extract_urls("curl https://github.com") == ["https://github.com"]


def test_extract_urls_multiple():
    cmd = "wget https://a.com/x ftp://b.local/file ssh://git@c.com/repo"
    urls = _extract_urls(cmd)
    assert len(urls) == 3
    assert "https://a.com/x" in urls
    assert "ftp://b.local/file" in urls
    assert "ssh://git@c.com/repo" in urls


def test_extract_urls_none():
    assert _extract_urls("yum install htop") == []
    assert _extract_urls("") == []


# --- _extract_host_from_url --- #

def test_extract_host_simple():
    assert _extract_host_from_url("https://github.com/x") == "github.com"
    assert _extract_host_from_url("http://10.0.0.5:8080/x") == "10.0.0.5"
    assert _extract_host_from_url("ssh://git@github.com/repo") == "github.com"


def test_extract_host_invalid():
    assert _extract_host_from_url("not-a-url") == ""
    assert _extract_host_from_url("") == ""


# --- _command_needs_public_network --- #

def test_needs_public_returns_tuple():
    result = _command_needs_public_network("uname -a")
    assert result == (False, "")


def test_needs_public_explicit_public_url():
    needs, reason = _command_needs_public_network("curl https://github.com")
    assert needs is True
    assert "github.com" in reason


def test_needs_public_explicit_internal_url():
    needs, reason = _command_needs_public_network("curl http://10.0.0.5:8080/x")
    assert needs is False


def test_needs_public_no_url_keyword_conservative():
    needs, reason = _command_needs_public_network("yum install -y htop")
    assert needs is True
    assert "mirror" in reason.lower() or "internet" in reason.lower()


def test_needs_public_safe_command():
    needs, reason = _command_needs_public_network("uname -a")
    assert needs is False
    assert reason == ""


def test_needs_public_allow_internal_mirror_bypasses():
    needs, reason = _command_needs_public_network(
        "curl https://github.com", allow_internal_mirror=True
    )
    assert needs is False
    assert reason == ""


def test_needs_public_empty_command():
    needs, reason = _command_needs_public_network("")
    assert needs is False
    assert reason == ""


def test_needs_public_pip_internal_index_allowed():
    needs, reason = _command_needs_public_network(
        "pip install -i http://pypi.corp/simple requests"
    )
    assert needs is False


def test_needs_public_pip_public_index_blocked():
    needs, reason = _command_needs_public_network(
        "pip install -i https://pypi.org/simple requests"
    )
    assert needs is True


def test_needs_public_mixed_urls_any_public_blocks():
    needs, reason = _command_needs_public_network(
        "wget http://internal.corp/file1 https://github.com/file2"
    )
    assert needs is True
    assert "github.com" in reason


def test_needs_public_ssh_internal_allowed():
    needs, reason = _command_needs_public_network(
        "git clone ssh://git@gitlab.internal/repo"
    )
    assert needs is False
