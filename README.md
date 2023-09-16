# docker-seafile-client
Docker image for Seafile terminal client.

### Docker-compose example:
```yaml
services:
  seafile-client:
    restart: always
    image: snegov/seafile-client
    environment:
      - LIBRARY_ID="79867cbf-2944-488d-9105-852463ecdf9e:my_library"
      - SERVER_HOST=seafile.example.com
      - USERNAME=user
      - PASSWORD=password
      - SEAFILE_UID=1000
      - SEAFILE_GID=100
    hostname: dsc
    volumes:
      - /home/johndow/seafile:/dsc/seafile
      - sync-data:/dsc/seafile-data
    container_name: seafile-client

volumes:
  sync-data:
```

### Environment variables:
 - `LIBRARY_ID` - library to sync, ID or name. Multiple libraries could be separated by colon `:`.
 - `SERVER_HOST` - hostname of your Seafile server, eg: `seafile.example.com`. If you're using non-standard port, you can specify it here, eg: `seafile.example.com:8080`.
 - `USERNAME`/ `PASSWORD` - credentials to access Seafile server.
 - `SEAFILE_UID` / `SEAFILE_GID` - UID/GID of user inside container. You can use it to set permissions on synced files. Default values are `1000`/`1000`.

### Volumes:
 - `/dsc/seafile-data`  Seafile client data directory (sync status, etc).
 - `/dsc/seafile`       Seafile libraries content.


### Some notes
`LIBRARY_ID` could be library ID or library name. Library ID is a 36-character string, which is a part of URI when you open library in webUI. Library name is a name you gave to library when you created it.

Libraries will be synced in subdirectories of `/dsc/seafile` directory inside container. You can mount it to host directory to access files.

`hostname` parameter is optional, but it's recommended to set it to some unique value, it will be shown in Seafile webUI as client name (`terminal-dsc` in given example).

`sync-data` volume is optional too, but it's recommended to use it. Otherwise, sync status will be lost when container is recreated.

