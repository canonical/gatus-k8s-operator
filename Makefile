# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

CHARM_NAME := gatus-k8s
IMAGE_NAME := gatus-test:latest
ROCK_PATH := gatus_rock

.PHONY: pack
pack:
	# Update requirements.txt
	@tox -e reqs > /dev/null
	# Build charm with 12-factor extension
	@CHARMCRAFT_ENABLE_EXPERIMENTAL_EXTENSIONS=true \
	charmcraft pack

.PHONY: build-rock
build-rock:
	# Clear existing rocks
	cd $(ROCK_PATH) && rm -f *.rock
	# Pack rock
	rockcraft pack
	# Push rock to local registry
	ROCK_NAME=$$(ls *.rock 2>/dev/null | head -n 1); \
	if [ -z "$$ROCK_NAME" ]; then \
		echo "No .rock file found."; \
		exit 1; \
	fi; \
	rockcraft.skopeo --insecure-policy copy --dest-tls-verify=false oci-archive:$$(ls *.rock) docker://localhost:32000/$(IMAGE_NAME)

.PHONY: integration-test
integration-test: ## Run integration tests
	tox -e integration -- --gatus-image localhost:32000/$(IMAGE_NAME)

.PHONY: deploy
deploy: # build-rock pack ## re-pack and re-deploy charm & rock
	juju remove-application gatus-k8s --force
	juju deploy ./$(CHARM_NAME)_amd64.charm --resource app-image=localhost:32000/$(IMAGE_NAME)

.PHONY: publish
.ONESHELL:
publish: #pack ## Publish charm
	@echo "Add rock image to registry"
	rockcraft.skopeo --insecure-policy copy oci-archive:$$(ls $(ROCK_PATH)/*.rock) docker-daemon:$(IMAGE_NAME)

	@echo "Push charm to charmhub"
	CHARM_MESSAGE=$$(charmcraft upload ./$(CHARM_NAME)_amd64.charm)
	CHARM_VERSION=$$(echo "$$CHARM_MESSAGE" | awk '{print $$2}')
	@echo "$$CHARM_MESSAGE"
	@echo "Charm revision: $$CHARM_VERSION"

	@echo "Get rock image digest"
	DIGEST=$$(docker inspect --format='{{.Id}}' $(IMAGE_NAME))
	@echo "Image digest: $$DIGEST"

	# Add image digest to charm
	RESOURCE_MESSAGE=$$(charmcraft upload-resource $(CHARM_NAME) app-image --image=$$DIGEST)
	RESOURCE_VERSION=$$(echo "$RESOURCE_MESSAGE" | awk '{print $$2}')
	@echo "$$RESOURCE_MESSAGE"
	@echo "Resource revision: $$RESOURCE_VERSION"

	# Release charm
	charmcraft release gatus-k8s \
		--revision=$${CHARM_VERSION} \
		--channel=edge \
		--resource app-image=app-image:$${RESOURCE_VERSION}
