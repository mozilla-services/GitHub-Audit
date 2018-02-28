#!/usr/bin/env python
"""
    Report on branches that don't match protection guidelines
"""
_epilog = """
"""
import argparse  # noqa: E402
import collections  # noqa: E402
import copy  # noqa: E402
import json  # noqa: E402
import logging  # noqa: E402
import os  # noqa: E402
import time  # noqa: E402
from agithub.GitHub import GitHub  # noqa: E402
# import github3  # noqa: E402
# import tinydb

DEBUG = False
CREDENTIALS_FILE = '.credentials'


class AG_Exception(Exception):
    pass


def ag_call(func, *args, expected_rc=None, **kwargs):
    """
    Wrap AGitHub calls with basic error detection.

    Not smart, and hides any error information from caller.
    But very convenient. :)
    """
    if expected_rc is None:
        expected_rc = [200, ]
    rc, body = func(*args, **kwargs)
    if rc not in expected_rc:
        if DEBUG:
            import pudb; pudb.set_trace()  # noqa: E702
        else:
            raise AG_Exception
    return body


def ag_get_all(func, *orig_args, **orig_kwargs):
    """
    Generator for multi-page GitHub responses

    It hacks the "page" query parameter to each call to get the next page. This
    is Not a general solution - it does not follow the links in the headers
    like a good client should.
    """
    kwargs = copy.deepcopy(orig_kwargs)
    args = copy.deepcopy(orig_args)
    kwargs["page"] = 1
    while True:
        body = ag_call(func, *args, **kwargs)
        if len(body) >= 1:
            for elem in body:
                yield elem
        else:
            break
        # fix up to get next page
        kwargs["page"] += 1


def get_github_client():
    def get_token():
        token = ''
        with open(CREDENTIALS_FILE, 'r') as cf:
            cf.readline()  # skip first line
            token = cf.readline().strip()
        return token

    token = get_token()
    #  gh = github3.login(token=token)
    gh = GitHub(token=token)
    gh.generateAuthHeader()
    return gh


def ratelimit_dict():
    #  return gh.ratelimit_remaining
    body = ag_call(gh.rate_limit.get)
    return body


def ratelimit_remaining():
    body = ratelimit_dict()
    return body["resources"]["core"]["remaining"]


def wait_for_ratelimit(min_karma=25, msg=None):
    while gh:
        payload = ag_call(gh.rate_limit.get)
        if payload["resources"]["core"]["remaining"] < min_karma:
            core = payload['resources']['core']
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
            for all branches
                ouput default branch protection
"""


gh = None


def harvest_repo(repo):
    full_name = repo["full_name"]
    name = repo["name"]
    owner = repo["owner"]
    default_branch = repo["default_branch"]
    protected_count = len(list(ag_get_all(gh.repos[full_name].branches.get,
                                          protected='true')))
    details = {
        "owner": owner,
        "name": name,
        "default_branch": default_branch,
        "protected_branch_count": protected_count,
    }
    # if repo is empty, branch retrieval will fail with 404
    try:
        branch = ag_call(gh.repos[full_name].branches[default_branch].get)
        logger.debug("Raw data for %s: %s", default_branch,
                     json.dumps(branch, indent=2))
        protection = ag_call(gh.repos[full_name]
                             .branches[default_branch].protection.get,
                             expected_rc=[200, 404])
        logger.debug("Protection data for %s: %s", default_branch,
                     json.dumps(protection, indent=2))
        signatures = ag_call(gh.repos[full_name]
                             .branches[default_branch]
                             .protection.required_signatures.get,
                             headers={"Accept":
                                      "application/vnd.github"
                                      ".zzzax-preview+json"},
                             expected_rc=[200, 404])
        logger.debug("Signature data for %s: %s", default_branch,
                     json.dumps(signatures, indent=2))
        details.update({
            "default_protected": bool(branch["protected"]),
            "protections": protection or None,
            "signatures": signatures or None,
        })
    except AG_Exception:
        # Assume no branch so add no data
        pass
    return {repo["full_name"]: details}


def harvest_org(org_name):
    logger.debug("Working on org '%s'", org_name)
    org_data = {}
    try:
        org = ag_call(gh.orgs[org_name].get)
    except AG_Exception:
        logger.error("No such org '%s'", org_name)
        return org_data
    for repo in ag_get_all(gh.orgs[org["login"]].repos.get):
        wait_for_ratelimit()
        repo_data = harvest_repo(repo)
        org_data.update(repo_data)
    return org_data


def process_orgs(args=None):
    logger.info("Gathering branch protection data."
                " (calls remaining %s).", ratelimit_remaining())
    if not args:
        args = {}
    results = {}
    for org in args.org:
        wait_for_ratelimit()
        if args.repo:
            logger.info("Only processing repo %s", args.repo)
            repo = ag_call(gh.repos[org][args.repo].get)
            org_data = harvest_repo(repo)
        else:
            org_data = harvest_org(org)
        results.update(org_data)
    logger.info("Finshed gathering branch protection data"
                " (calls remaining %s).", ratelimit_remaining())
    return results


def main(driver=None):
    args = parse_args()
    global gh
    gh = get_github_client()
    wait_for_ratelimit()
    body = ag_call(gh.user.get)
    collected_as = body["login"]
    logger.info("Running as {}".format(collected_as))
    data = process_orgs(args)
    results = {
        "collected_as": collected_as,
        "collected_at": time.time(),
    }
    results.update(data)
    print(json.dumps(results, indent=2))


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, epilog=_epilog)
    parser.add_argument("org", help='Organization',
                        default=['mozilla-services'],
                        nargs='*')
    parser.add_argument('--repo', help='Only check for this repo')
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
