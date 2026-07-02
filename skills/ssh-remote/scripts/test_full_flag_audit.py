"""Audit ALL global flags for both pre- and post-sub-command placement."""

import sys
sys.path.insert(0, '.')

from ssh_ops import _build_parser

# Each case: (flag_parts, dest, expected_value, sub_args)
# flag_parts is the list of tokens for the flag (may be 1 for store_true, 2 for value flags)
CASES = [
    # store_true flags (just the flag, no value token)
    (['--trust-host'],              'trust_host',           True,   ['test']),
    (['--no-password-with-key'],    'no_password_with_key',  True,   ['test']),
    (['--yes'],                     'yes',                  True,   ['exec', 'ls']),
    (['--i-know'],                  'i_know',               True,   ['test']),
    (['--insecure'],                'insecure',             True,   ['test']),
    (['--allow-internal-mirror'],   'allow_internal_mirror', True,  ['test']),
    (['--allow-public-probe'],      'allow_public_probe',   True,   ['test']),
    (['--no-cleanup'],              'no_cleanup',           True,   ['test']),
    (['--cleanup-dry-run'],         'cleanup_dry_run',      True,   ['test']),
    # int flags (flag + value token)
    (['--port', '2222'],            'port',                 2222,   ['test']),
    (['--timeout', '99'],           'timeout',              99,     ['test']),
    (['--transfer-timeout', '30'],  'transfer_timeout',     30,     ['test']),
    (['--cmd-timeout', '45'],       'cmd_timeout',          45,     ['exec', 'ls']),
    # string flags (flag + value token)
    (['--host', '1.2.3.4'],         'host',                 '1.2.3.4', ['test']),
    (['--user', 'alice'],           'user',                 'alice',   ['test']),
    (['--label', 'mylabel'],        'label',                'mylabel', ['test']),
    (['--password', 'secret123'],   'password',             'secret123', ['test']),
    (['--key-file', '/tmp/k'],      'key_file',             '/tmp/k',  ['test']),
    (['--host-key', '/tmp/h'],      'host_key',             '/tmp/h',  ['test']),
    (['--remote-staging-dir', '/var/tmp'], 'remote_staging_dir', '/var/tmp', ['test']),
    (['--local-staging-dir', '/srv/tmp'],  'local_staging_dir',  '/srv/tmp', ['test']),
]


def test_flag_before_subcommand():
    for tokens, dest, expected, sub_args in CASES:
        parser = _build_parser()
        args = parser.parse_args(tokens + sub_args)
        got = getattr(args, dest)
        assert got == expected, (
            f'BEFORE: flag {tokens[0]} expected {expected!r}, got {got!r}'
        )


def test_flag_after_subcommand():
    for tokens, dest, expected, sub_args in CASES:
        parser = _build_parser()
        sub_cmd, *rest = sub_args
        args = parser.parse_args([sub_cmd] + tokens + rest)
        got = getattr(args, dest)
        assert got == expected, (
            f'AFTER: flag {tokens[0]} expected {expected!r}, got {got!r}'
        )


def test_defaults_when_no_flag():
    parser = _build_parser()
    args = parser.parse_args(['test'])
    assert args.yes is False
    assert args.port == 22
    assert args.timeout == 15
    assert args.transfer_timeout == 600
    assert args.cmd_timeout == 600
    assert args.host is None
    assert args.user is None
