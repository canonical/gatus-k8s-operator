# gatus-k8s-operator
A [12-factor charm](https://documentation.ubuntu.com/juju/3.6/reference/charm/#factor-app-charm)
operator for running [Gatus](https://github.com/TwiN/gatus) on Juju and Kubernetes.

Gatus is a tool for monitoring service uptimes.

## Usage

To deploy Gatus in a Juju model, run:

```sh
juju deploy gatus-k8s --channel=edge
```

## Configuration

### 1. Postgresql relation
Simply run: 

```sh
juju integrate gatus-k8s postgresql-k8s
```
The charm automatically generates a few environment variables, 
including `POSTGRESQL_DB_CONNECT_STRING`. If this one exists and is non-empty, 
a `storage.yaml` file is created with the appropriate values.

The connection to Postgresql can be further customized with the `jdbc-parameters`
charm config:

```sh
juju config gatus-k8s jdbc-parameters="sslmode=disable"
```

If the Postgresql relation is not present, no `storage.yaml` file is created,
and Gatus defaults to in-memory execution.

### 2. Endpoints and announcements
These are simple charm configs that take YAML files as input.
Check `tests/integration/data/[endpoints|announcements].yaml` for examples.

```sh
juju config gatus-k8s announcements=@./tests/integration/data/announcements.yaml
```

### 3. Alerting
Currently, the charm supports Mattermost alerting.

Since alerts use webhook URLs that can be sensitive (anyone with the URL can send a message),
they are configured using Juju secrets. To do so, create a secret with a `mattermost-webhook-url`
key and add that secret ID to the `mattermost-alerting` charm config.
The charm unpacks the secret and passes it as an environment variable to the rock script.

```sh
juju add-secret gatus-secret mattermost-webhook-url="https://your.mattermost.instance/hooks/yourwebhookid"
juju grant-secret yoursecretid gatus-k8s
juju config gatus-k8s mattermost-alerting="yoursecretid"
```

## Development and testing

See [CONTRIBUTING.md](CONTRIBUTING.md).
