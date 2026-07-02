"""Verify global flags work both BEFORE and AFTER the sub-command.

Regression test for the argparse quirk where common flags inherited via
parents= were silently overridden by the sub-parser's default value when
placed before the sub-command. SmartArgumentParser fixes this by pre-parsing
common flags and merging non-default values back into the result.
"""

import sys
sys.path.insert(0, '.')

from ssh_ops import _build_parser


def test_flag_before_subcommand():
    """--yes placed BEFORE 'exec' must set args.yes = True."""
    parser = _build_parser()
    args = parser.parse_args(['--yes', 'exec', 'ls'])
    assert args.yes is True, f"expected yes=True, got {args.yes}"
    assert args.cmd == 'exec'
    assert args.command == 'ls'


def test_flag_after_subcommand():
    """--yes placed AFTER 'exec' must also set args.yes = True."""
    parser = _build_parser()
    args = parser.parse_args(['exec', '--yes', 'ls'])
    assert args.yes is True, f"expected yes=True, got {args.yes}"
    assert args.cmd == 'exec'
    assert args.command == 'ls'


def test_no_value_flag_before_subcommand():
    """Flags without values (--trust-host) work before the sub-command."""
    parser = _build_parser()
    args = parser.parse_args(['--trust-host', 'test'])
    assert args.trust_host is True, f"expected trust_host=True, got {args.trust_host}"
    assert args.cmd == 'test'


def test_no_value_flag_after_subcommand():
    """Flags without values work after the sub-command too."""
    parser = _build_parser()
    args = parser.parse_args(['test', '--trust-host'])
    assert args.trust_host is True, f"expected trust_host=True, got {args.trust_host}"
    assert args.cmd == 'test'


def test_valued_flag_before_subcommand():
    """--session ALPHA before the sub-command is preserved."""
    parser = _build_parser()
    args = parser.parse_args(['--session', 'ALPHA', 'exec', 'ls'])
    assert args.session == 'ALPHA', f"expected session=ALPHA, got {args.session}"
    assert args.cmd == 'exec'


def test_valued_flag_after_subcommand():
    """--session ALPHA after the sub-command is preserved."""
    parser = _build_parser()
    args = parser.parse_args(['exec', '--session', 'ALPHA', 'ls'])
    assert args.session == 'ALPHA', f"expected session=ALPHA, got {args.session}"
    assert args.cmd == 'exec'


def test_default_when_no_flag():
    """When --yes is omitted, args.yes is False regardless of position rules."""
    parser = _build_parser()
    args = parser.parse_args(['exec', 'ls'])
    assert args.yes is False


def test_help_works_for_subcommand():
    """ssh_ops.py exec --help should not crash."""
    parser = _build_parser()
    try:
        parser.parse_args(['exec', '--help'])
    except SystemExit:
        pass  # --help causes SystemExit, which is expected
