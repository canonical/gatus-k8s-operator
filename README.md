# gatus-k8s-operator
A charmed operator for running Gatus on Kubernetes.

(This is a work in progress.)

## Testing

First, install dependencies. Install
[uv](https://docs.astral.sh/uv/getting-started/installation/) and
then run the following command.

```bash
uv sync
```

To run linting, unit tests and static analysis.

```bash
tox
```

To run integration tests, run the following command. This builds a fresh rock
and uses it to run the tests.

```bash
make integration-test
```

## Deployment

Pack the charm:

```bash
make pack
```

Deploy the charm:

```bash
juju deploy ./gatus-k8s_amd64.charm --resource app-image=gatus/gatus:latest
```
