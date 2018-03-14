
PATH_TO_FOXSEC := ../foxsec
PATH_TO_METADATA := services/metadata
TMP_DIR := .cache

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


$(TMP_DIR)/repos_used_by_service.json: $(TMP_DIR)/services.json all_repo_results.combined.csv
	# turn the url into an owner/repository string,
	# with trailing ',' for better grep results
	# until
	./extract_service_results.py $(TMP_DIR)/services.json all_repo_results.combined.csv >$@

services: $(TMP_DIR)/repos_used_by_service.json

.PHONY: services clean
