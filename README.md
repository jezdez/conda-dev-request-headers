# conda-dev-request-headers

`conda-dev-request-headers` is a small development-only conda plugin for adding
scoped HTTP headers to conda's network requests. It is useful when testing
private channels, local package gateways, or authentication flows without
patching conda itself.

The plugin uses conda's public request-header plugin hooks:

- `conda_session_headers(host)` for host-wide headers
- `conda_request_headers(host, path)` for path-scoped headers

## Installation

Install it into the same environment that provides `conda`:

```shell
python -m pip install git+https://github.com/jezdez/conda-dev-request-headers.git
```

## Configuration

The recommended pattern is to keep scoped rules in trusted conda/user config and
read secret values from named environment variables. This mirrors tools such as
npm and pnpm, where the config names the registry and `${TOKEN}` supplies the
secret at runtime.

Create a local rules file:

```text
# ~/.config/conda/dev-request-headers
packages.example.test Authorization "Bearer ${CONDA_PACKAGES_TOKEN}"
packages.example.test/private X-Channel-Scope private
*.internal.example.test X-Developer alice
```

Then point the plugin at it:

```shell
export CONDA_DEV_REQUEST_HEADERS_FILE="$HOME/.config/conda/dev-request-headers"
export CONDA_PACKAGES_TOKEN="development-token"
```

You can also configure the file through conda's plugin settings in `.condarc`
under `plugins.*`:

```yaml
plugins:
  dev_request_headers_file: ~/.config/conda/dev-request-headers
```

Or put non-secret rules directly in `.condarc`:

```yaml
plugins:
  dev_request_headers:
    - 'packages.example.test Authorization "Bearer ${CONDA_PACKAGES_TOKEN}"'
```

For short-lived CI jobs, inline line-based rules are supported:

```shell
export CONDA_DEV_REQUEST_HEADERS='packages.example.test Authorization "Bearer ${CONDA_PACKAGES_TOKEN}"'
```

Avoid putting literal secrets in `CONDA_DEV_REQUEST_HEADERS`; use `${...}`
placeholders and pass the actual secret through your shell, CI secret store, or
password manager.

Selectors support:

- `*` for every host
- `example.com` for an exact host
- `example.com:8443` for an exact host and port
- `*.example.com` for subdomains
- `example.com/path` or `https://example.com/path` for a path prefix

Host-wide selectors are emitted through `conda_session_headers` so conda can
cache them efficiently. Selectors with a path prefix are emitted through
`conda_request_headers`.

If multiple matching rules set the same header, later rules win. Source order is:

1. `plugins.dev_request_headers` conda plugin setting
2. `plugins.dev_request_headers_file` conda plugin setting
3. `CONDA_DEV_REQUEST_HEADERS_FILE`
4. `CONDA_DEV_REQUEST_HEADERS`

## Security Notes

This plugin is intended for local development. Prefer host-specific selectors
over `*` so credentials are not sent to unrelated channels.

The plugin validates header names and rejects values containing CR, LF, or NUL
characters. It also ignores forbidden request headers such as `Host`, `Cookie`,
`Content-Length`, `Proxy-*`, and `Sec-*` rather than handing them to conda.

Secrets are read from the process environment and are never logged by the
plugin. Avoid committing shell scripts, `.env` files, or CI logs containing
literal secret values. If a rules file contains literal secrets instead of
`${...}` placeholders, keep it outside project repositories and restrict its
permissions.

## License

BSD-3-Clause. See [LICENSE](LICENSE).
