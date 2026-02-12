from logging import error as log_error, info as log_info
from os import path as ospath, environ
from subprocess import run as srun
from requests import get as rget
from dotenv import load_dotenv
from urllib.parse import urlparse, urlunparse

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
    try:
        parsed_url = urlparse(UPSTREAM_REPO)

        # Determine the hostname (e.g., github.com)
        # If hostname is None (e.g. invalid URL), fallback to original
        hostname = parsed_url.hostname if parsed_url.hostname else parsed_url.netloc

        if hostname:
            # Construct authenticated netloc
            if len(GITHUB_USERNAME) > 0:
                new_netloc = f"{GITHUB_USERNAME}:{GITHUB_TOKEN}@{hostname}"
            else:
                new_netloc = f"{GITHUB_TOKEN}@{hostname}"

            # Reconstruct URL ensuring HTTPS scheme
            # urlunparse takes (scheme, netloc, path, params, query, fragment)
            UPSTREAM_REPO = urlunparse(('https', new_netloc, parsed_url.path, parsed_url.params, parsed_url.query, parsed_url.fragment))
    except Exception as e:
        log_error(f"Failed to construct authenticated URL: {e}")
        # Proceed with original URL if parsing fails

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
