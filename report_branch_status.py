#!/usr/bin/env python
"""
    Report on branches that don't match protection guidelines from local json
    data.
"""
import argparse
import collections
import csv
import json
import logging
import os
import re
import sys
import time

import tinydb

_help_epilog = """
Currently checks for the following checkboxes to be enabled on the default
branch:
    Protect this branch
    Restrict who can commit to this branch
    Require signed commits
    Include Administrators
"""
DEBUG = False
logger = logging.getLogger(__name__)

Pseudo_code = """
    for all orgs
        for all repos
            check restrictions
            ouput default branch protection
"""

Repo = collections.namedtuple('Repo', "name protected restricted enforcement"
                              " signed team_used".split())


def get_nested(eventual_obj, *keys, default=None):
    for key in keys:
        try:
            eventual_obj = eventual_obj[key]
        except (KeyError, TypeError):
            eventual_obj = default
    return eventual_obj


def collect_status(gh, repo_doc):
    q = tinydb.Query()
    repo_url = repo_doc['url']
    default_branch = repo_doc['body']['default_branch']
    branch_url = f"{repo_url}/branches/{default_branch}"
    name = get_nested(repo_doc, 'body', 'full_name')

    branch_doc = gh.get(q.url.matches(branch_url))
    protected = get_nested(branch_doc, 'body', 'protected', default=False)

    # rest come from protection response
    protection_url = f"{branch_url}/protection"
    protection_doc = gh.get(q.url.matches(protection_url))
    # protections apply to admins
    enforcement = get_nested(protection_doc, 'body', "enforce_admins",
                                "enabled", default=False)
    # limit commits to default
    num_teams = len(get_nested(protection_doc, 'body', "restrictions",
                                "teams", default=[]))
    num_users = len(get_nested(protection_doc, 'body', "restrictions",
                                "users", default=[]))
    limited_commits = bool(num_teams + num_users > 0)

    # commits signed comes from signature doc
    sig_url = f"{protection_url}/required_signatures"
    sig_doc = gh.get(q.url.matches(sig_url))
    signing_required = get_nested(sig_doc, 'body', "enabled",
                                    default=False)
    # prefer team restrictions
    team_preferred = num_teams > 0 and num_users == 0
    repo = Repo(name, protected, limited_commits, enforcement,
                signing_required, team_preferred)
    return repo


def report_repos(args, report_lines):
    writer = csv.writer(sys.stdout)
    if args.header:
        writer.writerow(Repo._fields)
    writer.writerows(report_lines)


def of_interest(args, repo_document):
    result = True
    if args.only:
        repo_name = get_nested(repo_document, 'body', 'full_name')
        result = repo_name in args.only
    return result


def get_repos(table):
    """
    Generator for all repository documents in table

    yields document for repo URL query
    """
    repo_pat = r'^/repos/[^/]+/[^/]+$'
    q = tinydb.Query()
    for el in table.search(q.url.matches(repo_pat)):
        yield el


def main(driver=None):
    args = parse_args()
    repo_status = []
    with tinydb.TinyDB(args.infile[0].name) as db:
        gh = db.table('GitHub')
        for repo in get_repos(gh):
            if of_interest(args, repo):
                status = collect_status(gh, repo)
                repo_status.append(status)

    report_repos(args, repo_status)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, epilog=_help_epilog)
    parser.add_argument('--debug', help='Enter pdb on problem',
                        action='store_true')
    parser.add_argument("infile", help="input json file",
                        type=argparse.FileType(), nargs=1, default=sys.stdin)
    parser.add_argument("--only", action="append",
                        help="only include these owner/repo")
    parser.add_argument("--header", action="store_true",
                        help="Print CSV headers")
    args = parser.parse_args()
    global DEBUG
    DEBUG = args.debug
    if DEBUG:
        logger.setLevel(logging.DEBUG)
    return args


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(levelname)s: %(message)s')
    try:
        rc = main()
    except (KeyboardInterrupt, BrokenPipeError):
        rc = 2
    raise SystemExit(rc)
