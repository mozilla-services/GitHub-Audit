#!/usr/bin/env python3
"""
    Search for a term in the code of an org or repo, display any hits
"""
import argparse
import copy
import json
import logging
import time
import urllib.parse

from agithub.GitHub import GitHub

help_epilog = """
Uses GitHub's search to find candidate repos, then searches for all current
matches.
"""

DEBUG = False
CREDENTIALS_FILE = ".credentials"


class AG_Exception(Exception):
    pass


# agithub utility functions
def ag_call(
    func, *args, expected_rc=None, new_only=True, headers=None, no_cache=False, **kwargs
):
    """
    Wrap AGitHub calls with basic error detection

    Not smart, and hides any error information from caller.
    But very convenient. :)
    """

    def query_string():
        return urllib.parse.quote_plus(kwargs["q"])

    if not headers:
        headers = {}
    url = func.keywords["url"]
    # Insert our (possibly modified) headers
    real_headers = kwargs.setdefault("headers", {})
    real_headers.update(headers)

    if expected_rc is None:
        expected_rc = [200, 304]
    rc, body = func(*args, **kwargs)
    # If we have new information, we want to use it (and store it unless
    # no_cache is true)
    # If we are told our existing info is ok, or there's an error, use the
    # stored info
    # Handle repo rename/removal corner cases
    if rc == 301:
        logger.error("Permanent Redirect for '{}'".format(url))
        # TODO: do something better, like switch to using id's
        # for now, act like nothing is there
        body = []
    elif rc == 403 and rc not in expected_rc:
        # don't throw on this one, but do show query string
        # for search, there is a seperate rate limit we don't yet take into
        # account:
        #  https://developer.github.com/v3/search/#rate-limit
        logger.error("403 for query string '{}'".format(query_string()))
        logger.error("response: '{}'".format(repr(body)))
        expected_rc.append(rc)
    elif rc == 404 and rc not in expected_rc:
        logger.error("No longer available or access denied: {}".format(url))
        # TODO: Figure out what to do here. Maybe it's just that message, but
        # maybe need to delete from DB before next run
        body = []
        # don't throw on this one
        expected_rc.append(rc)
    logger.debug("{} for {}".format(rc, url))

    if rc not in expected_rc:
        if DEBUG:
            import pudb

            pudb.set_trace()  # noqa: E702
        else:
            logger.error("{} for {}".format(rc, url))
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
        # search results are ugly
        if isinstance(body, dict) and "items" in body and len(body["items"]) == 0:
            break
        elif not isinstance(body, list):
            yield body
        elif len(body) >= 1:
            for elem in body:
                yield elem
        else:
            break

        # fix up to get next page, without changing query set
        kwargs["page"] += 1
        kwargs["new_only"] = False


# JSON support routines
class BytesEncoder(json.JSONEncoder):
    # When reading from the database, an empty value will sometimes be returned
    # as an empty bytes array. Convert to empty string.
    def default(self, obj):
        if isinstance(obj, bytes):
            if not bool(obj):
                return ""
        return self.super(obj)


def get_github_client():
    def get_token():
        token = ""
        with open(CREDENTIALS_FILE, "r") as cf:
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
    body = ag_call(gh.rate_limit.get, no_cache=True)
    return body


def ratelimit_remaining():
    body = ratelimit_dict()
    return body["resources"]["core"]["remaining"]


def wait_for_ratelimit(min_karma=25, msg=None):
    while gh:
        payload = ag_call(gh.rate_limit.get, no_cache=True)
        if payload["resources"]["core"]["remaining"] < min_karma:
            core = payload["resources"]["core"]
            now = time.time()
            nap = max(core["reset"] - now, 0.1)
            logger.info("napping for %s seconds", nap)
            if msg:
                logger.info(msg)
            time.sleep(nap)
        else:
            break


logger = logging.getLogger(__name__)

Pseudo_code = """
    for all orgs
        search for term
        for all repos in result
            clone repo (shallow)
            grep repo
"""


# SHH, globals, don't tell anyone
gh = None


def matching_repos(scope, term):
    """
    Generator for repositories containing term
    """
    q = term + " in:file"
    if "/" in scope:
        q += " repo:{}".format(scope)
    else:
        q += " user:{}".format(scope)
    kwargs = {"q": q}
    found_repos = set()
    for body in ag_get_all(gh.search.code.get, **kwargs):
        if "items" not in body:
            # 403 or something we don't expect
            logger.error("Unexpected keys: {}".format(" ".join(body.keys())))
            break
        logger.debug("items in body: {}".format(len(body["items"])))
        for match in body["items"]:
            repo = match["repository"]["full_name"]
            if repo not in found_repos:
                found_repos.add(repo)
                yield repo
            else:
                logger.debug("another hit for {}".format(repo))


def main(driver=None):
    args = parse_args()
    global gh
    gh = get_github_client()
    wait_for_ratelimit()
    body = ag_call(gh.user.get)
    collected_as = body["login"]
    logger.info(
        "Running as {} ({} API calls remaining)".format(
            collected_as, ratelimit_remaining()
        )
    )
    for scope in args.scopes:
        logger.info("Starting on {}".format(scope))
        for repo in matching_repos(scope, args.term):
            print(repo)
    logger.info("Done with {} API calls remaining".format(ratelimit_remaining()))


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, epilog=help_epilog)
    parser.add_argument("--term", help="Term to search for", required=True)
    parser.add_argument("scopes", help="User or User/Repo", default=[], nargs="+")
    parser.add_argument("--debug", help="Enter pdb on problem", action="store_true")
    args = parser.parse_args()
    global DEBUG
    DEBUG = args.debug
    if DEBUG:
        logger.setLevel(logging.DEBUG)
    return args


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s"
    )
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit
