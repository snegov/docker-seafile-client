#!/bin/bash

set -e
set -u
set -o pipefail

DATA_DIR="${DATA_DIR:-/data}"
SEAFILE_UID="${SEAFILE_UID:-1000}"
SEAFILE_GID="${SEAFILE_GID:-1000}"

get () {
    NAME="$1"
    JSON="$2"
    # Tries to regex setting name from config. Only works with strings for now
    VALUE=$(echo $JSON | grep -Po '"'"$NAME"'"\s*:\s*.*?[^\\]"+,*' | sed -n -e 's/.*: *"\(.*\)",*/\1/p')
    # Use eval to ensure that nested expressens are executed (config points to environment var)
    eval echo $VALUE
}

setup_lib_sync(){
    if [ ! -d $DATA_DIR ]; then
      echo "Using new data directory: $DATA_DIR"
      mkdir -p $DATA_DIR
      chown seafile:seafile -R $DATA_DIR
    fi
    TOKEN_JSON=$(curl -d "username=$USERNAME" -d "password=$PASSWORD" ${SERVER_URL}:${SERVER_PORT}/api2/auth-token/ 2> /dev/null)
    TOKEN=$(get token "$TOKEN_JSON")
    LIBS_IN_SYNC=$(su - seafile -c 'seaf-cli list')
    LIBS=(${LIBRARY_ID//:/ })
    for i in "${!LIBS[@]}"
    do
      LIB="${LIBS[i]}"
      LIB_JSON=$(curl -G -H "Authorization: Token $TOKEN" -H 'Accept: application/json; indent=4' ${SERVER_URL}:${SERVER_PORT}/api2/repos/${LIB}/ 2> /dev/null)
      LIB_NAME=$(get name "$LIB_JSON")
      LIB_NAME_NO_SPACE=${LIB_NAME// /_}
      LIB_DIR=${DATA_DIR}/${LIB_NAME_NO_SPACE}
      set +e
      LIB_IN_SYNC=$(echo "$LIBS_IN_SYNC" | grep "$LIB")
      set -e
      if [ ${#LIB_IN_SYNC} -eq 0 ]; then
        echo "Syncing $LIB_NAME"
        mkdir -p $LIB_DIR
        chown seafile:seafile -R $LIB_DIR
        su - seafile -c "seaf-cli sync -l \"$LIB\" -s \"${SERVER_URL}:${SERVER_PORT}\" -d \"$LIB_DIR\" -u \"$USERNAME\" -p \"$PASSWORD\""
      fi
    done
}

setup_uid(){
    # Setup user/group ids
    if [ ! "$(id -u seafile)" -eq "${SEAFILE_UID}" ]; then
        # Change the SEAFILE_UID
        usermod -o -u "${SEAFILE_UID}" -g "${SEAFILE_GID}" seafile
    fi
}

keep_in_foreground() {
  while true; do
    tail -f /seafile-client/.ccnet/logs/seafile.log
  done
}

setup_uid
su - seafile -c "seaf-cli start"
sleep 10
setup_lib_sync
keep_in_foreground
