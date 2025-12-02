# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

CHARM_NAME := $(shell yq '.name' charmcraft.yaml)
ROCK_PATH := gatus_rock
ARCH := amd64
REGISTRY := localhost:32000

ROCK_VERSION := $(shell yq '.version' $(ROCK_PATH)/rockcraft.yaml)
ROCK_NAME := $(shell yq '.name' $(ROCK_PATH)/rockcraft.yaml)
ROCK_FILE := $(ROCK_NAME)_$(ROCK_VERSION)_$(ARCH).rock
ROCK_IMAGE := $(ROCK_NAME):$(ROCK_VERSION)
CHARM_FILE := $(CHARM_NAME)_$(ARCH).charm


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
	rockcraft clean copy-files
	rockcraft pack
	# Push rock to local registry
	rockcraft.skopeo --insecure-policy copy \
		--dest-tls-verify=false oci-archive:$(ROCK_FILE) \
		docker://$(REGISTRY)/$(ROCK_IMAGE)

.PHONY: integration-test
integration-test: ## Run integration tests
	tox -e integration -- --gatus-image $(REGISTRY)/$(ROCK_IMAGE)

.PHONY: deploy
deploy: # build-rock pack ## re-pack and re-deploy charm & rock
	juju remove-application gatus-k8s --force
	juju deploy ./$(CHARM_FILE) \
		--resource app-image=$(REGISTRY)/$(ROCK_IMAGE) \

.PHONY: refresh 
refresh: build-rock pack ## re-pack and re-deploy charm & rock
	juju refresh $(CHARM_NAME) \
		--path ./$(CHARM_FILE) \
		--resource app-image=$(REGISTRY)/$(ROCK_IMAGE)

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
