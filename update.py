from logging import error as log_error, info as log_info
from os import path as ospath, environ
from subprocess import run as srun
from requests import get as rget
from dotenv import load_dotenv

CONFIG_FILE_URL = environ.get('CONFIG_FILE_URL')
try:
    if len(CONFIG_FILE_URL) == 0:
        raise TypeError
    try:
        res = rget(CONFIG_FILE_URL)
        if res.status_code == 200:
            with open('config.env', 'wb+') as f:
                f.write(res.content)
        else:
            log_error(f"Failed to download config.env {res.status_code}")
    except Exception as e:
        log_error(f"CONFIG_FILE_URL: {e}")
except:
    pass

load_dotenv('config.env', override=True)

UPSTREAM_REPO = environ.get('UPSTREAM_REPO', '')
if len(UPSTREAM_REPO) == 0:
    UPSTREAM_REPO = "https://github.com/IbrahimKhan2004/TgFileSharingBot"

UPSTREAM_BRANCH = environ.get('UPSTREAM_BRANCH', '')
if len(UPSTREAM_BRANCH) == 0:
    UPSTREAM_BRANCH = 'main'

GITHUB_TOKEN = environ.get('GITHUB_TOKEN', '')
GITHUB_USERNAME = environ.get('GITHUB_USERNAME', '')

if len(GITHUB_TOKEN) > 0:
    # Check if UPSTREAM_REPO starts with http/https and strip it
    if UPSTREAM_REPO.startswith('https://'):
        repo_url = UPSTREAM_REPO.replace('https://', '')
    elif UPSTREAM_REPO.startswith('http://'):
        repo_url = UPSTREAM_REPO.replace('http://', '')
    else:
        repo_url = UPSTREAM_REPO

    # Construct authenticated URL
    if len(GITHUB_USERNAME) > 0:
        UPSTREAM_REPO = f"https://{GITHUB_USERNAME}:{GITHUB_TOKEN}@{repo_url}"
    else:
        UPSTREAM_REPO = f"https://{GITHUB_TOKEN}@{repo_url}"

if ospath.exists('.git'):
    srun(["rm", "-rf", ".git"])

update = srun([f"git init -q \
                 && git config --global user.email desmondmile166@gmail.com \
                 && git config --global user.name Johnmclane5 \
                 && git add . \
                 && git commit -sm update -q \
                 && git remote add origin {UPSTREAM_REPO} \
                 && git fetch origin -q \
                 && git reset --hard origin/{UPSTREAM_BRANCH} -q"], shell=True)

if update.returncode == 0:
    log_info('Successfully updated with latest commit from UPSTREAM_REPO')
else:
    log_error('Something went wrong while updating, check UPSTREAM_REPO if valid or not!')
