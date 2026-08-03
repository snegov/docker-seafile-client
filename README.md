# docker-seafile-client
Docker image for [Seafile CLI client](https://help.seafile.com/syncing_client/linux-cli/).

Image on Docker Hub:
 [snegov/seafile-client](https://hub.docker.com/r/snegov/seafile-client).

### Docker-compose example:
Also available as a ready-to-use [`compose.example.yaml`](compose.example.yaml).

```yaml
services:
  seafile-client:
    restart: always
    image: snegov/seafile-client:0.0.13
    environment:
      LIBRARY_ID: "79867cbf-2944-488d-9105-852463ecdf9e:my_library"
      SERVER_HOST: seafile.example.com
      USERNAME: user
      PASSWORD: password
      SEAFILE_UID: 1000
      SEAFILE_GID: 100
    hostname: dsc
    volumes:
      - /home/johndow/seafile:/dsc/seafile
      - sync-data:/dsc/seafile-data
    container_name: seafile-client

volumes:
  sync-data:
```

### Environment variables:
 - `LIBRARY_ID` - library to sync, ID or name. Multiple libraries could be
 separated by colon `:`.
 - `SERVER_HOST` - hostname of your Seafile server, eg: _seafile.example.com_.
 If you're using non-standard port, you can specify it here,
 eg: _seafile.example.com:8080_.
 - `USERNAME` / `PASSWORD` - credentials to access Seafile server.
 - `PASSWORD_FILE` - path to a file holding the password, for Docker Compose
 and Swarm secrets. Use either `PASSWORD` or `PASSWORD_FILE`, never both.
 - `TOKEN` / `TOKEN_FILE` - an API token to authenticate with instead of a
 password. A token takes precedence over a password and can be revoked on the
 server. Use either `TOKEN` or `TOKEN_FILE`, never both.
 - `SEAFILE_UID` / `SEAFILE_GID` - UID/GID of user inside container. You can
 use it to set permissions on synced files. Default values are _1000_ / _1000_.
 - `DELETE_CONFIRM_THRESHOLD` - represents the number of files that require
 confirmation before being deleted simultaneously. Default value is _500_.
 - `DISABLE_VERIFY_CERTIFICATE` - set to _true_ to disable server's certificate
 verification. Default value is _false_. Booleans accept _true_/_false_,
 _1_/_0_, _yes_/_no_ and _on_/_off_, in any case. Note that this setting had no
 effect in released images up to and including 0.0.13: whatever you set the
 variable to, the client stored the string `True`, and the Seafile daemon
 accepts only the lowercase string `true`, so verification stayed on even when
 the variable was set. The default was never affected, because the string
 `False` is also not `true`.
 - `UPLOAD_LIMIT` / `DOWNLOAD_LIMIT` -  upload/download speed limit in B/s
 (bytes per second). Default values are _0_ (unlimited).

Numeric variables must be whole, non-negative numbers. A malformed or negative
 value stops the container at startup with a message naming the variable,
 rather than being passed on to the Seafile client.

### Using Docker secrets:
Mount the secret and point `PASSWORD_FILE` at it, so the password never enters
 the environment:

```yaml
services:
  seafile-client:
    environment:
      PASSWORD_FILE: /run/secrets/seafile_password
    secrets:
      - seafile_password

secrets:
  seafile_password:
    file: ./seafile_password.txt
```

A trailing newline in the file is ignored; everything else, including
 surrounding spaces, is part of the secret.

The client authenticates `seaf-cli` with an API token rather than the account
 password, so the password never appears in a command line. The token does
 appear there, and command lines are visible to any process in the container.
 This is a limitation of `seaf-cli`, which accepts credentials only as
 arguments. A token can at least be revoked on the server.

### Volumes:
 - `/dsc/seafile-data`  Seafile client data directory (sync status, etc).
 - `/dsc/seafile`       Seafile libraries content.


### Some notes
`LIBRARY_ID` could be library ID or library name. Library ID is a 36-character
 string, which is a part of URI when you open library in webUI. Library name is
 a name you gave to library when you created it.

Libraries will be synced in subdirectories of `/dsc/seafile` directory inside
 container. You can mount it to host directory to access files.

The subdirectory is named after the library, with whitespace replaced by
 underscores. A library is skipped with a warning when its name cannot be a
 directory of its own: an empty name, `.`, `..`, or a name containing `/`. Two
 libraries whose names would produce the same directory both get their library
 ID appended, so they never share one. Everything is created under the
 libraries directory (`/dsc/seafile`, or the deprecated `/data` when that
 exists); a library name can never place it elsewhere.

The container stops gracefully on `docker stop`: it shuts the Seafile daemon
 down and exits with code 0. It exits with a nonzero code and an explanatory
 message when the daemon fails to start or stop within its timeout, instead of
 waiting forever.

`hostname` parameter is optional, but it's recommended to set it to some unique
 value, it will be shown in Seafile webUI as client name (`terminal-dsc` in
 given example).

`sync-data` volume is optional too, but it's recommended to use it. Otherwise,
 sync status will be lost when container is recreated.

At the moment there is no suitable way to confirm deletion of large number of
 files. So, if you're going to delete a lot of files, you should set
 `DELETE_CONFIRM_THRESHOLD` to some larger value.

### Links
- [Official Seafile CLI client documentation](https://help.seafile.com/syncing_client/linux-cli/)
