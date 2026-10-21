#!/usr/bin/env bash
# ==============================================================================
# n8n Auto Git Push Script (Production Nightly Workflow Backup)
# Schedule: Midnight every night (Asia/Bangkok)
# Target Repo: /home/captain/n8n-docker -> git@github.com:eatal9937/n8n-docker.git
# ==============================================================================

set -uo pipefail

REPO_DIR="/home/captain/n8n-docker"
LOG_DIR="${REPO_DIR}/logs"
LOG_FILE="${LOG_DIR}/git_push.log"
BRANCH="main"
REMOTE="origin"
CONTAINER_NAME="n8n_captain"

mkdir -p "${LOG_DIR}"

log() {
    local timestamp
    timestamp=$(TZ="Asia/Bangkok" date +"%Y-%m-%d %H:%M:%S ICT")
    echo "[${timestamp}] $*" | tee -a "${LOG_FILE}"
}

log "=================================================="
log "Starting automated nightly Git push for n8n workflows"

cd "${REPO_DIR}" || {
    log "ERROR: Cannot change directory to ${REPO_DIR}"
    exit 1
}

# 1. Remove stale git index lock if process died previously
if [ -f "${REPO_DIR}/.git/index.lock" ]; then
    log "WARNING: Found stale .git/index.lock, checking if git is running..."
    if ! pgrep -x git >/dev/null; then
        rm -f "${REPO_DIR}/.git/index.lock"
        log "Removed stale .git/index.lock"
    fi
fi

# 2. Export live workflows from running n8n container
if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    log "Exporting workflows from live container (${CONTAINER_NAME})..."
    
    # Run n8n CLI export inside container
    docker exec -u node "${CONTAINER_NAME}" rm -rf /tmp/workflows_export 2>/dev/null || true
    docker exec -u node "${CONTAINER_NAME}" mkdir -p /tmp/workflows_export
    
    if docker exec -u node "${CONTAINER_NAME}" n8n export:workflow --backup --output=/tmp/workflows_export/ >/dev/null 2>&1; then
        # Copy exported files to host temp
        rm -rf /tmp/n8n_workflows_tmp
        docker cp "${CONTAINER_NAME}:/tmp/workflows_export" /tmp/n8n_workflows_tmp
        
        # Format and save into workflows/ directory with friendly names
        python3 - << 'PYEOF'
import os, json, glob, re

src = "/tmp/n8n_workflows_tmp"
dst = "/home/captain/n8n-docker/workflows"
os.makedirs(dst, exist_ok=True)

count = 0
for f in glob.glob(os.path.join(src, "*.json")):
    try:
        with open(f, "r", encoding="utf-8") as fp:
            d = json.load(fp)
        name = d.get("name") or os.path.basename(f)
        clean = re.sub(r'[/\\?%*:|"<> ]+', "_", name).strip("_") + ".json"
        with open(os.path.join(dst, clean), "w", encoding="utf-8") as out:
            json.dump(d, out, indent=2, ensure_ascii=False)
        count += 1
    except Exception as e:
        print(f"Error mapping {f}: {e}")
print(f"Successfully processed {count} workflows.")
PYEOF
        rm -rf /tmp/n8n_workflows_tmp
        log "Workflows exported and synced to ${REPO_DIR}/workflows/"
    else
        log "WARNING: n8n export command inside container failed. Skipping export step."
    fi
else
    log "WARNING: Container ${CONTAINER_NAME} is not running. Using existing workflow files on disk."
fi

# 3. Clean up junk files
find . -name "._*" -type f -delete 2>/dev/null || true

# 4. Check git status
CHANGES=$(git status --porcelain)

if [ -n "${CHANGES}" ]; then
    log "Detected changes to commit:"
    echo "${CHANGES}" | sed 's/^/  /' | tee -a "${LOG_FILE}"

    git add workflows/ scripts/ docker-compose.yml .gitignore

    COMMIT_DATE=$(TZ="Asia/Bangkok" date +"%Y-%m-%d %H:%M:%S ICT")
    COMMIT_MSG="chore(backup): auto nightly sync n8n workflows [captain] - ${COMMIT_DATE}"

    if git commit -m "${COMMIT_MSG}"; then
        log "Committed changes: ${COMMIT_MSG}"
    else
        log "ERROR: Git commit failed"
        exit 1
    fi
else
    log "Working tree clean. No workflow modifications to commit."
fi

# 5. Pull latest remote changes with rebase
log "Pulling latest changes from ${REMOTE}/${BRANCH} with rebase..."
if ! git pull --rebase --autostash "${REMOTE}" "${BRANCH}" 2>&1 | tee -a "${LOG_FILE}"; then
    log "ERROR: Git pull --rebase failed! Aborting rebase to preserve local state..."
    git rebase --abort 2>/dev/null || true
    exit 1
fi

# 6. Check if local is ahead of remote and push
AHEAD=$(git rev-list --count "${REMOTE}/${BRANCH}..HEAD" 2>/dev/null || echo "0")

if [ "${AHEAD}" -gt 0 ]; then
    log "Pushing ${AHEAD} commit(s) to ${REMOTE}/${BRANCH}..."
    if git push "${REMOTE}" "${BRANCH}" 2>&1 | tee -a "${LOG_FILE}"; then
        log "SUCCESS: Pushed n8n workflows to GitHub successfully."
    else
        log "ERROR: Git push failed! Please check SSH key and network connectivity."
        exit 1
    fi
else
    log "Remote is already up to date. Nothing to push."
fi

log "Automated nightly Git push for n8n completed."
log "=================================================="

# Keep log file size reasonable (keep last 2000 lines if log > 3000 lines)
if [ -f "${LOG_FILE}" ] && [ $(wc -l < "${LOG_FILE}") -gt 3000 ]; then
    tail -n 2000 "${LOG_FILE}" > "${LOG_FILE}.tmp" && mv "${LOG_FILE}.tmp" "${LOG_FILE}"
fi
