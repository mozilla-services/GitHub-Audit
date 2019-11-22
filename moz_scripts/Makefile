# Makefile to collect data

.DEFAULT_GOAL := help

CACHE_DIR := .cache

SERVICE_ORGS := \
	Mozilla-Games \
	MozillaReality \
	MozillaSecurity \
	iodide-project \
	mozilla \
	mozilla-bteam \
	mozilla-conduit \
	mozilla-extensions \
	mozilla-frontend-infra \
	mozilla-mobile \
	mozilla-platform-ops \
	mozilla-releng \
	mozilla-services \
	mozilla-standards \
	mozilla-tw \
	nss-dev \
	taskcluster \


OTHER_ORGS := \
	mozilla-b2g \
	mozilla-partners \


SERVICE_DBS := $(SERVICE_ORGS:=.db.json)
OTHER_DBS := $(OTHER_ORGS:=.db.json)

ALL_ORGS := $(SERVICE_ORGS) $(OTHER_ORGS)
ALL_DBS := $(SERVICE_DBS) $(OTHER_DBS)

# Sometimes we'll be working with non-current files, so allow date to be
# overridden
DATE := $(shell date --utc --iso )

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
	@echo "  preview_new_issues     show what open_protected_issues would do"
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
	@echo "  s3_upload   upload the .db.json files to S3"

list:
	@echo $(ALL_ORGS)
	@echo $(SERVICE_DBS)

clean:
	rm -f *.json consolidated.csv

get: $(SERVICE_DBS)
get_others: $(OTHER_DBS)
get_all: $(ALL_DBS)

#_full_common: report consolidate store
_full_common: s3_prep s3_upload
full: clean get _full_common
full_others: clean get_others _full_common
full_all: clean get_all _full_common

report:
	moz_scripts/report-by-service

consolidated.csv \
consolidate:
	@echo "You must manually copy the latest report CSV to consolidated.csv"
	@false

preview_new_issues: consolidated.csv
	moz_scripts/open_issues.py               $$(grep '/' consolidated.csv | cut -d, -f1,2 --output-delimiter '/')

open_protected_issues: consolidated.csv
	moz_scripts/open_issues.py --open-issues $$(grep '/' consolidated.csv | cut -d, -f1,2 --output-delimiter '/')

s3_prep:
	bash -c ' \
		tmp_dir=$$(mktemp -d /tmp/$${USER}-GitHub-Audit-S3-XXXXXX) ; \
		echo Using $$tmp_dir for work ; \
		for f in *.db.json ; do \
		    jq -erc ".GitHub[] | . + { \"date\": \"$(DATE)\" } " \
		    < $$f > $$tmp_dir/$(DATE)-$$f ; \
		    jq -erc ".| select(.body|objects)" \
		    < $$tmp_dir/$(DATE)-$$f  > $$tmp_dir/$(DATE)-$${f%.json}.obj.json ; \
		    jq -erc ".| select(.body|arrays)" \
		    < $$tmp_dir/$(DATE)-$$f  > $$tmp_dir/$(DATE)-$${f%.json}.arr.json ; \
		done ; \
		wc -lc $$tmp_dir/*.db.json ; \
		echo Using $$tmp_dir for work ; \
		'

s3_upload:
	test -d $$(ls -d /tmp/$${USER}-GitHub-Audit-S3-* | head -1)
	bash -cx ' \
		s3_dir=$$(ls -dt /tmp/$${USER}-GitHub-Audit-S3-* | head -1) && \
		pushd $$s3_dir && \
		for f in *db.json; do \
		    aws --profile cloudservices-aws-stage s3 cp $$f s3://foxsec-metrics/github/raw/ ; \
		done && \
		for f in *db.arr.json; do \
		    aws --profile cloudservices-aws-stage s3 cp $$f s3://foxsec-metrics/github/array_json/ ; \
		done && \
		for f in *db.obj.json; do \
		    aws --profile cloudservices-aws-stage s3 cp $$f s3://foxsec-metrics/github/object_json/ ; \
		done && \
		true \
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

.PHONY: list clean get report consolidate help s3_prep gen_ddl
