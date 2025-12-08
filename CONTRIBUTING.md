# Contributing

To make contributions to this charm, you'll need a working
[development setup](https://documentation.ubuntu.com/juju/3.6/howto/manage-your-deployment/#set-up-your-deployment-local-testing-and-development).

If using Multipass, you can use these scripts to get started:

```sh
# From the host machine
multipass launch \
	--cpus 8 \
	--disk 50G \
	--memory 16G \
	--name charm-dev \
	--mount [path to your charm repository] \
	24.04
multipass shell charm-dev
```

```sh
# From within the Multipass VM
sudo snap install rockcraft --channel latest/edge --classic
sudo snap install charmcraft --channel latest/edge --classic

sudo snap install lxd
lxd init --auto

sudo snap install microk8s --channel 1.31-strict/stable
sudo adduser $USER snap_microk8s

sudo microk8s enable hostpath-storage
sudo microk8s enable registry
sudo microk8s enable ingress

sudo microk8s status --wait-ready

sudo snap install juju --channel 3.6/stable
mkdir -p ~/.local/share
juju bootstrap microk8s dev-controller
juju add-model charm-dev

sudo apt update
sudo apt install -y build-essential libssl-dev

sudo snap install kubectl --classic
mkdir ~/.kube
sudo microk8s config > ~/.kube/config

curl -LsSf https://astral.sh/uv/install.sh | sh
uv python install 3.12
uv python update-shell
uv tool install tox

sudo snap install yq
```

```sh
# From within the cloned repository
uv venv
uv sync
```

## Build the rock and charm

Build the rock and charm in this git repository using:

```shell
# Builds the rock and the charm
make build-rock pack
```

## Local deployment

To deploy the charm locally, run:

```sh
# For the initial deployment, optionally also build the rock and pack the charm
make [build-rock pack] deploy
# To refresh the rock and charm (this always rebuilds the rock and repacks the charm)
make refresh
```

## Testing

This project uses `tox` for managing test environments. There are some pre-configured environments
that can be used for linting and formatting code when you're preparing contributions to the charm:

```sh
tox run -e format        # update your code according to linting rules
tox run -e lint          # code style
tox run -e static        # static type checking
tox run -e unit          # unit tests
tox                      # runs 'format', 'lint', 'static', and 'unit' environments
```

For integration tests, a `make` target is provided. You might want to build the rock
and pack the charm first, if changes to them have been made.

```sh
make [build-rock pack] integration-test
```


<!-- You may want to include any contribution/style guidelines in this document>
