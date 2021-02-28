# docker-seafile-client
Runs a seafile client in docker with possibility to sync seafile repositories.

## Docker-compose example:
```yaml
version: '3'

services:
  seafile-client:
    restart: always
    image: snegov/seafile-client
    environment:
      - LIBRARY_ID=<your-library-id-here>
      - SERVER_HOST=<server-host>
      - USERNAME=<username>
      - PASSWORD=<password>
      - SEAFILE_UID=<your_uid>
      - SEAFILE_GID=<your_gid>
    hostname: docker-seafile-client
    volumes:
      - seafile-data:/seafile-client/seafile-data
      - <host-volume-path>:/data

volumes:
  seafile-data:
```

Library id could be found from "My Libraries" page in Seafile webUI - link to each library contains library ID in it.

Inside container libraries' content will be put in `/data` directory, so map your host directory to it.

`hostname` parameter in docker-compose will set client name in Seafile's "Linked devices" admin page. Resulting name will be prefixed by "terminal-".

Also you could check [docker-compose example](docker-compose.example.yml).

## Environment variables:
 - `LIBRARY_ID=<your-library-id-here>`  ID of library to sync; multiple libraries could be separated by colon `:`.
 - `SERVER_HOST=<server-host>`          Hostname of your seafile server, eg: `seafile.example.com`. If you're using non-standart port, specify it here, eg: `seafile.example.com:8080`.
 - `USERNAME=<username>`                Seafile account username.
 - `PASSWORD=<password>`                Seafile account password.
 - `SEAFILE_UID=<uid>`                  Downloaded files will have this uid.
 - `SEAFILE_GID=<gid>`                  Downloaded files will have this gid.
