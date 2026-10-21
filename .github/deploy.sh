#!/bin/bash
# =============================================================================
# beerstat — deploy the consumer container on gunlinux.ru.
#
# Runs ON the server, invoked by .github/workflows/deploy.yaml over SSH with
# DEPLOY_TAG=<commit short SHA> exported. CI has already pushed the public
# image to Docker Hub, so this script only:
#
#   1. fast-forwards the deploy checkout to origin/master,
#   2. verifies the runtime `.env` exists (it is not in git),
#   3. pulls the pushed image,
#   4. installs deploy/beerstat.service with the tag and run uid baked in,
#   5. disables the legacy Python `bot@beer_consumer` unit,
#   6. (re)starts the `beerstat` container.
#
# Idempotent: safe to re-run.
#
# Prerequisite (one-time, on the server): a git clone of this repo at
# $REPO_DIR with a hand-written .env. The .env is gitignored and survives
# `git reset --hard`.
# =============================================================================
set -euo pipefail

REPO_DIR="/home/loki/projects/bot/beerstat"
BRANCH="master"
IMAGE="gunlinuxloki/beerstat"
UNIT="beerstat"
LEGACY_UNIT="bot@beer_consumer.service"

cd "$REPO_DIR" || exit 1

TAG="${DEPLOY_TAG:?DEPLOY_TAG is required (commit short SHA)}"

# --- 1. Pull the deployed commit ---------------------------------------------
git remote set-url origin git@github.com:gunlinux/beerstat.git
git fetch --all
git reset --hard "origin/$BRANCH"

# Guard: refuse to run against a commit that lacks the deploy artifacts.
if [ ! -f deploy/beerstat.service ]; then
    echo "ERROR: origin/$BRANCH lacks deploy/beerstat.service — refusing to deploy." >&2
    exit 1
fi

# --- 2. Guard the runtime config ---------------------------------------------
if [ ! -f .env ]; then
    echo "ERROR: $REPO_DIR/.env is missing (RABBIT_URL, BEER_URL, ...) — refusing to deploy." >&2
    exit 1
fi
for key in RABBIT_URL BEER_URL; do
    if ! grep -qE "^ *$key=.+" .env; then
        echo "ERROR: $key is unset in .env — refusing to deploy." >&2
        exit 1
    fi
done

# --- 3. Pull the pushed image ------------------------------------------------
# The Docker Hub repository is public, so the server needs no registry login.
docker pull "$IMAGE:$TAG" >/dev/null

# --- 4. Install the unit with the tag and the run uid baked in ----------------
UID_GID="$(id -u):$(id -g)"
sed -e "s|@IMAGE_TAG@|$TAG|g" -e "s|@RUN_UID@|$UID_GID|g" deploy/beerstat.service \
    | sudo tee "/etc/systemd/system/$UNIT.service" >/dev/null
sudo systemctl daemon-reload

# --- 5. Retire the old Python consumer ---------------------------------------
if systemctl list-unit-files "$LEGACY_UNIT" --no-legend 2>/dev/null | grep -q .; then
    sudo systemctl disable --now "$LEGACY_UNIT" >/dev/null 2>&1 || true
fi

# --- 6. (Re)start the consumer ------------------------------------------------
sudo systemctl enable "$UNIT.service" >/dev/null

# Restart when the running image differs from the deployed tag; `start` is a
# no-op for the already-running matching container.
CURRENT="$(docker inspect --format '{{.Config.Image}}' "$UNIT" 2>/dev/null || true)"
if [ "$CURRENT" != "$IMAGE:$TAG" ]; then
    sudo systemctl restart "$UNIT.service"
else
    sudo systemctl start "$UNIT.service"
fi

sleep 3
if ! docker ps --format '{{.Names}}' | grep -qx "$UNIT"; then
    echo "WARNING: container $UNIT is not running — check: journalctl -u $UNIT" >&2
    sudo journalctl -u "$UNIT.service" -n 20 --no-pager >&2 || true
    exit 1
fi

echo "Deployment completed: $IMAGE:$TAG"
echo "Follow the log with: sudo journalctl -u $UNIT -f"
