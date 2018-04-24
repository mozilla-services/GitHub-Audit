#!/usr/bin/env python
"""
    Report on whether 2FA is configured for an organization
"""
_epilog = """
"""
import argparse  # noqa: E402
import json  # noqa: E402
import logging  # noqa: E402
import os  # noqa: E402
import time  # noqa: E402
from github_selenium import GitHub2FA, WebDriverException  # noqa: E402
# import tinydb

URL_TEMPLATE = "https://github.com/organizations/ORG/settings/security"
GH_LOGIN = os.getenv('GH_LOGIN', "org_owner_login")
GH_PASSWORD = os.getenv('GH_PASSWORD', 'password')
DEBUG = False


logger = logging.getLogger(__name__)


class MFA_Configured(GitHub2FA):

    def __init__(self, *args, token=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.token = token

    def get_checkbox_status(self):
        checkbox = self.get_element('.form-checkbox > label:nth-child(1) > '
                                    'input:nth-child(1)')
        results = {'2FA_enabled': checkbox.is_selected()}
        return results

    def process_org(self, org):
        url = URL_TEMPLATE.replace('ORG', org)
        error = False
        try:
            self.login(GH_LOGIN, GH_PASSWORD, url, 'Security', self.token)
            results = self.get_checkbox_status()
            results['time'] = time.strftime('%Y-%m-%d %H:%M')
            results['org'] = org
            results['admin'] = GH_LOGIN
            print(json.dumps(results))
        except WebDriverException:
            error = True
            logger.fatal("Deep error on {} - did browser crash?".format(org))
        except ValueError as e:
            error = True
            logger.fatal("Navigation issue on {}: {}".format(org, e.args[0]))

        if DEBUG and error:
            try:
                import pudb as pdb
            except ImportError:
                import pdb
            pdb.set_trace()


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, epilog=_epilog)
    parser.add_argument("orgs", help='Organization(s) to check',
                        default=['mozilla'], nargs='*')
    parser.add_argument("--token", help='2fa token', default=None)
    parser.add_argument('--debug', help='Enter pdb on problem',
                        action='store_true')
    args = parser.parse_args()
    if not args.token:
        args.token = input("token please: ")
    global DEBUG
    DEBUG = args.debug
    if DEBUG:
        logger.setLevel(logging.DEBUG)
    return args


def process_orgs(driver=None, args={}):
    logger.info("Verifying 2FA mandated by orgs.")
    logger.info("Attempting login as '{}'.".format(GH_LOGIN))
    logger.info("  (if wrong, set GH_LOGIN & GH_PASSWORD in environment"
                " properly)")
    driver = MFA_Configured(headless=not DEBUG, token=args.token)
    for org in args.orgs:
        driver.process_org(org)
    driver.quit()
    logger.debug("Browser closed")


def main(driver=None):
    args = parse_args()
    process_orgs(driver, args)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit
