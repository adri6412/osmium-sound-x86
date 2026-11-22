#!/bin/bash
# Copia la UI Qt sul Dell e la compila la' (Debian 13, Qt 6.8.2 come l'immagine
# di produzione). Gli asset e le traduzioni sono quelli gia' installati in
# /opt/hifi-native-ui, condivisi con la UI in C.
set -euo pipefail
# Target dev box — no baked-in address or password (this ships in the shared
# core). Set HOST (required); USER_SSH defaults to the login name. PASS is
# optional: leave it unset to authenticate with your SSH key/agent (preferred);
# set it only on a throwaway box without keys, and it is read from the
# environment, never hardcoded here.
HOST=${HOST:?set HOST to the target box, e.g. HOST=192.168.0.x ./sync.sh}
USER=${USER_SSH:-ssh}
PASS=${PASS:-}
DEST=/home/ssh/native-ui-qt
SSHOPT="-o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no -o LogLevel=ERROR -o ConnectTimeout=10"
if [ -z "$PASS" ]; then
    # Key / agent auth: no password handling at all.
    RSH() { ssh $SSHOPT "$@"; }
    RCP() { scp $SSHOPT -q "$@"; }
elif command -v sshpass >/dev/null 2>&1; then
    RSH() { sshpass -p "$PASS" ssh $SSHOPT "$@"; }
    RCP() { sshpass -p "$PASS" scp $SSHOPT -q "$@"; }
else
    ASK=$(mktemp); printf '#!/bin/sh\necho %s\n' "$PASS" > "$ASK"; chmod +x "$ASK"
    trap 'rm -f "$ASK"' EXIT
    RSH() { SSH_ASKPASS="$ASK" SSH_ASKPASS_REQUIRE=force setsid -w ssh $SSHOPT -o NumberOfPasswordPrompts=1 "$@"; }
    RCP() { SSH_ASKPASS="$ASK" SSH_ASKPASS_REQUIRE=force setsid -w scp $SSHOPT -o NumberOfPasswordPrompts=1 -q "$@"; }
fi
cd "$(dirname "$0")"
RSH "$USER@$HOST" "mkdir -p $DEST/src $DEST/qml $DEST/icons $DEST/tools; rm -f $DEST/main.cpp"
RCP Makefile "$USER@$HOST:$DEST/"
RCP src/* "$USER@$HOST:$DEST/src/"
RCP qml/* "$USER@$HOST:$DEST/qml/"
# le icone: tutte (sono ~1 MB reali), cosi' non manca mai niente
RCP -r icons "$USER@$HOST:$DEST/"
RCP tools/devrun.sh "$USER@$HOST:$DEST/tools/"
RSH "$USER@$HOST" "cd $DEST && make -j2 2>&1 | grep -E 'error|Error|undefined' | head -30; ls -la hifi-qt | awk '{print \$5, \$9}'"
