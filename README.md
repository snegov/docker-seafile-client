# docker-seafile-client
Run a seafile client inside docker witch can sync files from seafile repositories

See docker-compose how to use.

## Docker-compose example:
```yaml
version: '3'
services:
  seafile-client:
    restart: always
    build: .
    container_name: seafile-client
    environment:
      - LIBRARY_ID=<your-library-id-here>
      - SERVER_HOST=<server-host>
      - SERVER_PORT=<server-port>
      - USERNAME=<username>
      - PASSWORD=<password>
      - DATA_DIR=<directory-path-to-sync>
      - SEAFILE_UID=<your_uid>
      - SEAFILE_GID=<your_gid>
    volumes:
      - <host-volume-path>:<directory-path-to-sync>
```

## Environment variables:
 - `LIBRARY_ID=<your-library-id-here>`  ID of library to sync; multiple libraries could be separated by colon `:`
 - `SERVER_HOST=<server-host>`          Hostname of your seafile server, eg: seafile.example.com
 - `SERVER_PORT=<server-port>`          Which port the server is hosted on: usually 443 (https) or 80 (http)
 - `USERNAME=<username>`                Seafile account username
 - `PASSWORD=<password>`                Seafile account password
 - `DATA_DIR=<directory-path-to-sync>`  The path where to put the files
 - `SEAFILE_UID=<uid>`                  Downloaded files will have this uid
 - `SEAFILE_GID=<gid>`                  Downloaded files will have this gid
