#!/usr/bin/env bash
# Script d'assistance pour monter Google Drive via rclone pour les tests System Orion sous Linux.

MOUNT_DIR="/home/titan/GoogleDrive"

echo "=== System Orion — Assistant de montage rclone Google Drive ==="

# 1. Vérification / création du répertoire
if [ ! -d "$MOUNT_DIR" ]; then
    mkdir -p "$MOUNT_DIR"
    echo "OK : Dossier $MOUNT_DIR créé."
fi

# 2. Dé-montage préventif si un point mort existe
fusermount -u "$MOUNT_DIR" 2>/dev/null || true

# 3. Lancement du montage rclone avec contournement DNS IPv6 (GODEBUG=netdns=cgo)
echo "Connexion et montage du volume remote 'gdrive:' sur $MOUNT_DIR..."
export GODEBUG=netdns=cgo
rclone mount gdrive: "$MOUNT_DIR" \
    --vfs-cache-mode writes \
    --daemon

sleep 2

# 4. Vérification du montage
if mountpoint -q "$MOUNT_DIR"; then
    echo "SUCCÈS : Google Drive est monté sur $MOUNT_DIR"
    echo "Vous pouvez maintenant sélectionner le mode 'Google Drive' dans System Orion !"
else
    echo "ATTENTION : Le montage a échoué. Vérifiez rclone avec : GODEBUG=netdns=cgo rclone lsd gdrive:"
fi
