# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

IMAGE_NAME := gatus-test:latest
ROCK_PATH := gatus_rock

.PHONY: build-rock
build-rock:
	# Clear existing rocks
	cd $(ROCK_PATH) && rm *.rock
	# Pack rock
	cd $(ROCK_PATH) && rockcraft pack
	# Push rock to local registry
	cd $(ROCK_PATH) && \
	ROCK_NAME=$$(ls *.rock 2>/dev/null | head -n 1); \
	if [ -z "$$ROCK_NAME" ]; then \
		echo "No .rock file found."; \
		exit 1; \
	fi; \
	rockcraft.skopeo --insecure-policy copy --dest-tls-verify=false oci-archive:$$(ls *.rock) docker://localhost:32000/$(IMAGE_NAME)

.PHONY: integration-test
integration-test: ## Run integration tests
	# tox -e integration -- --gatus-image localhost:32000/$(IMAGE_NAME)
	tox -e integration -- --gatus-image localhost:32000/gatus:0.5
