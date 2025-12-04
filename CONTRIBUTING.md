# Contributing

To make contributions to this charm, you'll need a working
[development setup](https://documentation.ubuntu.com/juju/3.6/howto/manage-your-deployment/#set-up-your-deployment-local-testing-and-development).

If using Multipass, you can use
[these scripts](https://gist.github.com/RenanGreca/935ed647ecc071bcb5882b03d2ec82d0)
to get started.

Additionally, you'll need some Python-based dependencies:

```sh
# From within the Multipass VM
curl -LsSf https://astral.sh/uv/install.sh | sh
uv python install 3.12
uv python update-shell
uv tool install tox

# From the cloned repository
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
