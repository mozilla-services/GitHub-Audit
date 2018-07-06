# GitHub-Audit

Report on GitHub organizations and repositories for adherence to
[Mozilla's Guidelines for Sensitive Repositories][guidelines_url]
(additional [background][background_url]).

<!-- I hope to do this in future, so leaving as template for now
[![Build Status][travis-image]][travis-url]
[![Downloads Stats][npm-downloads]][npm-url]
-->

GitHub-Audit is a set of scripts which can be used to query various
aspects of an organization or repository.

These scripts are intended to be usable both from the command line (CLI)
and via automation (using 12 Factor principles whenever possible).


## Installation

For now, users should clone the repository, and install the requirements
using [``pipenv``][pipenv_url]:

```sh
git clone https://GitHub.com/Mozilla-Services/GitHub-Audit
cd GitHub-Audit
pipenv install
```


## Usage example

All scripts should respond to the ``--help`` option. Additional options
are often described there.

### Checks via API

These checks require a PAT token available. The PAT
token should be on the second line of a file named ``.credentials`` in
the current directory (s/a #3).

Each of the scripts below supports a ``--help`` option. Use that for
additional information on invoking each script.

- ``get_branch_protections.py`` * to extract the information about
  protected branches. Outputs JSON file, which
  ``report_branch_status.py`` can summarize to csv. Import that into a
  spreadsheet, and play.

- ``show_all_terms`` is a wrapper script around ``term_search.py``. It
  makes local shallow clones of repos that match, and uses ``rg`` to
  search for additional occurances. Use the ``--help`` option.

- ``term_search.py`` search orgs or repos for a specific term, such as
  an API token name. Outputs list of repos that do have the term (per
  GitHub's index, which can be out of date).

_For more examples and usage, please refer to the [Wiki][wiki]._

## Development setup

### Prerequisites

This project uses [Black][black_url] to format all python code. A
``.pre-commit-config.yaml`` file is included, and use of the
[pre-commit][pre_commit_url] is recommended.

To ready your environment for development, do:
```sh
pipenv install --dev
pre-commit install
```

## Release History

See [Changes]

## License

Distributed under the Mozilla Public License, version 2 (MPL-2) license. See ``LICENSE`` for more information.

## Contributing

1. Discuss any new feature first by opening an issue.
1. Fork it (<https://github.com/mozilla-services/GitHub-Audit/fork>)
1. Clone your fork to your development environment.
2. Create your feature branch (`git checkout -b feature/fooBar`)
3. Commit your changes (`git commit -am 'Add some fooBar'`)
4. Push to the branch (`git push origin feature/fooBar`)
5. Create a new Pull Request

<!-- Markdown link & img dfn's -->
[wiki]: https://github.com/mozilla-services/Github-Audit/wiki
[black_url]: https://black.readthedocs.io/en/stable/index.html
[pre_commit_url]: https://pre-commit.com/
[pipenv_url]: https://docs.pipenv.org/
[guidelines_url]: https://wiki.mozilla.org/GitHub/Repository_Security
[background_url]: docs/README.md
