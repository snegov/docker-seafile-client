# docker-seafile-client
Run a seafile client inside docker witch can sync files from seafile repositories

See docker-compose how to use.

## Environment variables:
 - `LIBRARY_ID=<your-library-id-here>`  ID of library to sync; multiple libraries could be separated by colon `:`
 - `SERVER_HOST=<server-host>`          Hostname of your seafile server, eg: seafile.example.com
 - `SERVER_PORT=<server-port>`          Which port the server is hosted on: usually 443 (https) or 80 (http)
 - `USERNAME=<username>`                Seafile account username
 - `PASSWORD=<password>`                Seafile account password
 - `DATA_DIR=<directory-path-to-sync>`  The path where to put the files
 - `SEAFILE_UID=<uid>`                  Downloaded files will have this uid
 - `SEAFILE_GID=<gid>`                  Downloaded files will have this gid

## How to find library id:

<img src="imgs/help.png"/>
