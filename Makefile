
PATH_TO_FOXSEC := ../foxsec
PATH_TO_METADATA := services/metadata
TMP_DIR := .cache

REPO_JSON_FILES = $(wildcard *.db.json)
REPO_STATUS_FILES := $(REPO_JSON_FILES:.json=.json.csv)

%.db.json.csv: %.db.json
	./report_branch_status.py $< >$@

help:
	@echo "services: get/update data from metadata"
	@echo "clean: purge stuff"

clean:
	rm -rf $(TMP_DIR)


$(TMP_DIR)/services.json: $(PATH_TO_FOXSEC)/$(PATH_TO_METADATA)
	-mkdir -p $(TMP_DIR)
	# Flatten <file>.json:{sourceControl:[repo_urls]} to [[<file>, repo_urls]]
	bash -c ' \
	cd "$(PATH_TO_FOXSEC)/$(PATH_TO_METADATA)" ; \
	LANG=C ; \
	for f in [A-Z]*json ; do \
	    service="\"$${f%.json}\""  ; \
	    jq --compact-output ".sourceControl[] | [ $$service, . ]" $$f ; \
	done ' \
	> $@


$(TMP_DIR)/repos_used_by_service.csv: $(TMP_DIR)/services.json ${REPO_STATUS_FILES}
	./extract_service_results.py --services $(TMP_DIR)/services.json ${REPO_STATUS_FILES} >$@

services: $(TMP_DIR)/repos_used_by_service.csv

.PHONY: services clean
