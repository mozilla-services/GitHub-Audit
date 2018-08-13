#!/usr/bin/env bash

# Hack to get repos we care about

set -eu

CLONE_URL=git@github.com:mozilla-services/foxsec.git
CLONE_DIR=/tmp/repo-list

METADATA_PATH=services/metadata

if [[ ! -d $CLONE_DIR ]]; then
    git clone --depth 1 $CLONE_URL $CLONE_DIR &>/dev/null
    cd $CLONE_DIR
else
    cd $CLONE_DIR
    git fetch --depth 1 &>/dev/null    # fetch latest
    git reset --hard HEAD &>/dev/null  # ensure no mods
    git checkout origin/master &>/dev/null # get latest
fi

for f in $METADATA_PATH/*json; do
    echo $(basename ${f%.json})
    # Strip '.git' before sort or issues (see below)
    for r in $(jq -r '.sourceControl[]' $f |
	       sed -e 's,^https://github.com/,,' \
		   -e 's,\.git$,,' |
	       LC_ALL=en_US.UTF-8 sort --ignore-case ); do
	echo $r
    done
done

exit

_bogus=<<EOF

Long explanation about collation. Assume you have 2 repos with the same
prefix: 'abc' and 'abcdef'. We would expect these to sort in that order:
  abc
  abcdef

The actual value in the metadate is the repo's URL, which ends with
'.git'. Sorting 'abc.git' & 'abcdef.git' yields:
  abcdef.git
  abc.git

When you then strip the '.git', you end up with
  abcdef
  abc
which just looks wrong.

Solution: strip the '.git' prior to sort.

EOF
