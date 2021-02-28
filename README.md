# docker-seafile-client
Run a seafile client inside docker which can sync files from seafile repositories.

See [docker-compose](docker-compose.example.yml) how to use.

## Docker-compose example:
```yaml
version: '3'
services:
  seafile-client:
    restart: always
    image: snegov/seafile-client
    container_name: seafile-client
    environment:
      - LIBRARY_ID=<your-library-id-here>
      - SERVER_HOST=<server-host>
      - USERNAME=<username>
      - PASSWORD=<password>
      - SEAFILE_UID=<your_uid>
      - SEAFILE_GID=<your_gid>
    volumes:
      - <host-volume-path>:/data
```

Inside container libraries' content will be put in `/data` directory, so map your host directory to it.

## Environment variables:
 - `LIBRARY_ID=<your-library-id-here>`  ID of library to sync; multiple libraries could be separated by colon `:`
 - `SERVER_HOST=<server-host>`          Hostname of your seafile server, eg: seafile.example.com. If you're using non-standart port, specify it here, eg: seafile.example.com:8080
 - `USERNAME=<username>`                Seafile account username
 - `PASSWORD=<password>`                Seafile account password
 - `SEAFILE_UID=<uid>`                  Downloaded files will have this uid
 - `SEAFILE_GID=<gid>`                  Downloaded files will have this gid
