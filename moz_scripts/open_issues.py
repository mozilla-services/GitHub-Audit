#!/usr/bin/env python3
"""
Create issue in supplied org/repositories

We reopen an issue if it already exists
"""

import argparse
import copy
import logging
import time
import urllib.parse

from agithub.GitHub import GitHub

help_epilog = """
Uses GitHub's search to find existing issues, then reopens or creates one as
appropriate.
"""

DEBUG = False
CREDENTIALS_FILE = ".credentials"
MESSAGES_FILE = "messages.yaml"


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


# GitHub API v3 support
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


# finally, our app!
logger = logging.getLogger(__name__)

Pseudo_code = """
    for each repo
        search for existing issue
        if none:
            create new issue with message
        else if issue closed:
            reopen with message
        else:
            add message
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


class NoIssue(Exception):
    pass


def get_message(owner, repo):
    """
    Return a fully expanded message body & title

    ToDo: read from yaml file
    """
    title = "Set protected status on production branch"
    message = """
The production branch on this repository is not protected against \
force pushes. This setting is recommended as part of [Mozilla's \
Guidelines][guidelines_url] for a Sensitive Repository.

**Anyone with admin permissions for this repository can correct the \
setting using [this URL][protect_url].**

If you have any questions, or believe this issue was opened in \
error, please contact [us][email] and mention SOGH0001 and this repository.

Thank you for your prompt attention to this issue.
--Firefox Security Operations team

[guidelines_url]: https://wiki.mozilla.org/GitHub/Repository_Security
[protect_url]: https://github.com/{owner}/{repo}/settings/branches
[email]: <mailto:secops+github@mozilla.com?subject=SOGH0001+Question+re+\
{owner}/{repo}>
    """.format(
        **locals()
    ).strip()

    logger.debug("title: '%s'", title)
    logger.debug("message: '%s'", message)
    return title, message


def find_existing_issue(owner, repo):
    logger.warning("Search not yet implemented, will always open new issue")
    raise NoIssue


def update_issue(owner, repo, issue):
    """
        Update an existing issue, and make sure it is not closed.

        ToDo: consider different message text when reopening
              maybe prepend "REOPENED: " to title?
    """
    _, text = get_message(owner, repo)
    # open bug in case it was closed
    payload = {"state": "open"}
    func = gh.repos[owner][repo].issues[issue].patch
    url = func.keywords["url"]
    logger.debug("Commenting on %(issue)s via %(url)s", locals())
    if DRY_RUN:
        # multiple calls, all debug info out already, so bail
        return
    status, _ = func(body=payload)
    if status in [422]:
        logger.error("Could not reopen %(url)s. Likely no write permission.", locals())
    # add comment
    payload = {"body": text}
    gh.repos[owner][repo].issues[issue].comments.post(body=payload)
    return


def create_issue(owner, repo):
    """
        Create a new issue
    """
    title, text = get_message(owner, repo)
    payload = {"title": title, "body": text}
    func = gh.repos[owner][repo].issues.post
    url = func.keywords["url"]
    logger.debug("Opening new issue via %(url)s", locals())
    if DRY_RUN:
        # multiple calls, all debug info out already, so bail
        return
    status, _ = func(body=payload)
    if status not in [201]:
        logger.error("Issue not opened for %(url)s status %(status)s", locals())


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
    for repo_full_name in args.repos:
        logger.info("Starting on {}".format(repo_full_name))
        owner, repo = repo_full_name.split("/")
        try:
            issue = find_existing_issue(owner, repo)
            update_issue(owner, repo, issue)
        except NoIssue:
            create_issue(owner, repo)
    logger.info("Done with {} API calls remaining".format(ratelimit_remaining()))


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, epilog=help_epilog)
    parser.add_argument("repos", help="owner/repo to open issue on", nargs="+")
    parser.add_argument("--debug", help="log at DEBUG level", action="store_true")
    parser.add_argument("--dry-run", help="Do not open issues", action="store_true")
    args = parser.parse_args()

    global DEBUG, DRY_RUN
    DRY_RUN = args.dry_run
    DEBUG = args.debug or DRY_RUN
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
