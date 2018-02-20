#!/usr/bin/env python
"""
    Report on branches that don't match protection guidelines
"""
_epilog = """
"""
import argparse  # noqa: E402
import collections  # noqa: E402
import json  # noqa: E402
import logging  # noqa: E402
import os  # noqa: E402
import time  # noqa: E402
import github3  # noqa: E402
# import tinydb

GH_LOGIN = os.getenv('GH_LOGIN', "org_owner_login")
GH_TOKEN = os.getenv('GH_TOKEN', 'PAT')
DEBUG = False
CREDENTIALS_FILE = '.credentials'


def get_github3_client():
    def get_token():
        token = ''
        with open(CREDENTIALS_FILE, 'r') as cf:
            cf.readline()  # skip first line
            token = cf.readline().strip()
        return token

    token = get_token()
    gh = github3.login(token=token)
    return gh


def wait_for_karma(gh, min_karma=25, msg=None):
    while gh:
        if gh.ratelimit_remaining < min_karma:
            core = gh.rate_limit()['resources']['core']
            now = time.time()
            nap = max(core['reset'] - now, 0.1)
            logger.info("napping for %s seconds", nap)
            if msg:
                logger.info(msg)
            time.sleep(nap)
        else:
            break


logger = logging.getLogger(__name__)

Pseudo_code = """
    for all orgs
        for all repos
            if private, add all collaborators to set
            else (public) add all admin & write collaborators to set
    for all users in set
        get # ssh keys & gpg keys
        print if > 1, along with max role

    N.B. might run into limits
    N.B. not keeping history
"""

# Need an enaum for levels
# need


read_somewhere = set()
admin_somewhere = set()
write_somewhere = set()

gh = None


def harvest_repo(repo):
    results = {
        "repository": repo.full_name,
        "default_branch": repo.default_branch,
        "protected_branch_count": len(list(repo.branches(protected=True))),
    }
    branch = repo.branch(results["default_branch"])
    results.update({
        "default_protected": bool(branch.protected),
        "protections": branch.protection or None,
    })
    print(json.dumps(results))
    return results


def harvest_org(gh, org):
    org = gh.organization(org)
    for repo in org.repositories():
        wait_for_karma(gh)
        harvest_repo(repo)


def process_orgs(driver=None, args={}):
    logger.info("Finding branches out of compliance.")
    for org in args.org:
        wait_for_karma(gh)
        harvest_org(gh, org)


def main(driver=None):
    args = parse_args()
    global gh
    gh = get_github3_client()
    logger.info("Running as {}".format(gh.me().login))
    logger.info("  (if wrong, set proper GH_TOKEN in environtment"
                " properly)")
    process_orgs(driver, args)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, epilog=_epilog)
    parser.add_argument("org", help='Organization',
                        default=['mozilla-services'],
                        nargs='*')
    parser.add_argument('--debug', help='Enter pdb on problem',
                        action='store_true')
    args = parser.parse_args()
    global DEBUG
    DEBUG = args.debug
    if DEBUG:
        logger.setLevel(logging.DEBUG)
    return args


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(levelname)s: %(message)s')
    logging.getLogger('github3').setLevel(logging.WARNING)
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit
