# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

IMAGE_NAME := gatus-test:latest
ROCK_PATH := gatus_rock

.PHONY: pack
pack:
	# Update requirements.txt
	@tox -e reqs > /dev/null
	# Build charm with 12-factor extension
	CHARMCRAFT_ENABLE_EXPERIMENTAL_EXTENSIONS=true \
	charmcraft pack

.PHONY: build-rock
build-rock:
	# Clear existing rocks
	cd $(ROCK_PATH) && rm -f *.rock
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
integration-test: build-rock ## Run integration tests
	tox -e integration -- --gatus-image localhost:32000/$(IMAGE_NAME)
