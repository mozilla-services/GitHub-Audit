# Makefile to collect data

.DEFAULT_GOAL := help

CACHE_DIR := .cache

SERVICE_ORGS := \
	bugzilla \
	mozilla \
	mozilla-bteam \
	mozilla-conduit \
	mozilla-frontend-infra \
	mozilla-mobile \
	mozilla-releng \
	mozilla-services \
	taskcluster \

OTHER_ORGS := \
	mozilla-b2g \
	mozilla-neutrino \
	mozilla-partners \
	mozilla-platform-ops \

SERVICE_DBS := $(SERVICE_ORGS:=.db.json)
OTHER_DBS := $(OTHER_ORGS:=.db.json)

ALL_ORGS := $(SERVICE_ORGS) $(OTHER_ORGS)
ALL_DBS := $(SERVICE_DBS) $(OTHER_DBS)

# Local Static Rules
.PHONY: $(ALL_ORGS)
$(ALL_DBS) : %.db.json: %
	./get_branch_protections.py $@

help:
	@echo "Makefile to run repo status reports"
	@echo "run from parent directory as:"
	@echo "  make -f moz_scripts/Makefile"
	@echo ""
	@echo "Targets in this Makefile"
	@echo "  clean       remove data from prior runs"
	@echo "  get         obtain all data for service orgs"
	@echo "  report      build the per-service reports"
	@echo "  consolidate gather all per-service reports for spreadsheet import"
	@echo "              into consolidate.csv"
	@echo "  store       store latest data into foxsec-results"
	@echo "              (manual push required)"
	@echo "  open_protected_issues  open GitHub issues on repositories which"
	@echo "                         do not have branch protection enabled"
	@echo ""
	@echo "  get_others  obtain all data for non-service orgs"
	@echo "  get_all     obtain all data for all configured orgs"
	@echo ""
	@echo "  full        full workflow for service orgs"
	@echo "  full_others full workflow for non-service orgs"
	@echo "  full_all    full workflow for all configured orgs"
	@echo ""
	@echo "  s3_prep     prepare the .db.json files for upload into Athena"
	@echo "  gen_ddl     (re)generate the HIVE DDL needed to read data into Athena"
	@echo "              this likely needs to be done after any data additions"

list:
	@echo $(ALL_ORGS)
	@echo $(SERVICE_DBS)

clean:
	rm -f *.json consolidated.csv

get: $(SERVICE_DBS)
get_others: $(OTHER_DBS)
get_all: $(ALL_DBS)

_full_common: report consolidate store
full: clean get _full_common
full_others: clean get_others _full_common
full_all: clean get_all _full_common

report:
	moz_scripts/report-by-service

consolidated.csv \
consolidate:
	@# force the sort order we want
	env LANG=en_US.UTF-8 bash -c 'cat $$(ls -1td /tmp/$$USER-report-by-service-* | head -1)/*.csv' >consolidated.csv

open_protected_issues: consolidated.csv
	moz_scripts/open_issues.py $$(grep '/' consolidated.csv | cut -d, -f1,2 | grep False$$ | cut -d, -f1)

store:
	bash -c ' \
		tmp_dir=$$(mktemp -d /tmp/$${USER}-GitHub-Audit-git-XXXXXX) ; \
		echo Using $$tmp_dir for work ; \
		pushd $$tmp_dir &>/dev/null ; \
		git clone --depth 1 git+ssh://github.com/mozilla-services/foxsec-results ; \
		cd foxsec-results/github-configs ; \
		for f in ~1/*.db.json ; do \
		  jq . < $$f > $${f##*/} ; \
		done ; \
		git commit -am "$$(date +%F) github-configs update" ; \
		git log -n1 --stat \
		'
	@echo "Manually push from $$(ls -1td /tmp/$${USER}-GitHub-Audit-git-*/foxsec-results/ | head -1)"
	@echo "Forcing failure to ensure push done prior to anything else"
	false

s3_prep:
	sh -c ' \
		tmp_dir=$$(mktemp -d /tmp/$${USER}-GitHub-Audit-S3-XXXXXX) ; \
		echo Using $$tmp_dir for work ; \
		for f in *.db.json ; do \
		  jq -erc ".GitHub[] | del(.body.commit.commit.verification)" < $$f > $$tmp_dir/$$f ; \
		done ; \
		wc -lc $$tmp_dir/*.db.json \
		'

gen_ddl:
	test -d $$(ls -d /tmp/$${USER}-GitHub-Audit-S3-* | head -1)
	bash -c ' \
		s3_dir=$$(ls -dt /tmp/$${USER}-GitHub-Audit-S3-* | head -1) ; \
		orc-tools json-schema -p $$s3_dir/*.db.json \
			| sed -e "s,^  \(\S\+\):,  \`\1\` ," \
			-e "s,-,_,g" \
			-e "s,^\(\s\+\)\(\S\+\):,\1\`\2\`:," \
			-e "s,\`\`,\`,g" \
			-e "s,binary,string," \
			-e "s,smallint,int," \
			-e "s,timestamp,string," \
			-e "s,tinyint,int," \
			-e "s,uniontype<>,string," \
			-e 1d \
			-e "\$$s,>>,>," \
			> /tmp/schema.txt \
		'

.PHONY: list clean get report consolidate help store s3_prep gen_ddl
