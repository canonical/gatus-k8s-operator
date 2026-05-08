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
Run: 

```sh
juju integrate gatus-k8s postgresql-k8s
```
The charm automatically generates a few environment variables, 
including `POSTGRESQL_DB_CONNECT_STRING`. If this one exists and is non-empty, 
a `storage.yaml` file is created with the appropriate values.

If the Postgresql relation is not present, no `storage.yaml` file is created,
and Gatus defaults to in-memory execution.

### 2. Endpoints and announcements
These are charm configs that take YAML files as input.
Check `tests/data/[endpoints|announcements].yaml` for examples.

```sh
juju config gatus-k8s announcements=@./tests/data/announcements.yaml
juju config gatus-k8s endpoints=@./tests/data/endpoints.yaml
```

### 3. Alerting
Currently, the charm supports Mattermost alerting.

Since alerts use webhook URLs that can be sensitive (anyone with the URL can send a message),
they are configured using Juju secrets. To do so, create a secret containing a `default` key with the webhook URL.
Add that secret ID to the `mattermost-alerting` charm config.
The charm unpacks the secret and passes it as an environment variable to the rock script.

```sh
juju add-secret mattermost-alerting default="https://your.mattermost.instance/hooks/yourwebhookid"
juju grant-secret yoursecretid gatus-k8s
juju config gatus-k8s mattermost-alerting="yoursecretid"
```

You can add additional webhook URLs to the `mattermost-alerting` juju secret, with keys named
after the channels you want to send alerts to (e.g. `channel-name: "https://your.mattermost.instance/hooks/yourwebhookid"`).
Then, these keys need to be mentioned in the endpoint configuration, as follows:

```yaml
# mattermost-alerting-secret.yaml
default: "https://your.mattermost.instance/hooks/yourwebhookid"
channel-name: "https://your.mattermost.instance/hooks/yourwebhookid"
```

```yaml
# endpoints.yaml
endpoints:
  # ... Existing endpoints
  - name: "" # User-facing name
    # ... Existing configuration
    alerts:
      - type: mattermost
        # ... Existing configuration
        provider-override:
          webhook-url: "[webhook-url:channel-name]"
```

The charm will automatically replace the `[webhook-url:channel-name]` placeholders with the actual webhook URLs.

### 4. OIDC authentication

The charm supports OIDC authentication via a relation to a charm offering the `oauth` interface, such as [hydra](https://charmhub.io/hydra).

```sh
juju deploy hydra
juju relate gatus-k8s hydra
```

The charm will automatically configure Gatus to use the OIDC provider.

Optionally, a list of authorized users can be added via the `oidc-allowed-subjects` config.

The full setup of an OIDC authentication flow is out of scope for this README.
For more information about the Canonical Identity Platform, see relevant [documentation](https://canonical-identity.readthedocs-hosted.com/reference/canonical-identity-platform-architecture/).

## Development and testing

See [CONTRIBUTING.md](CONTRIBUTING.md).
