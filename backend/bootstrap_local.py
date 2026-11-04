"""Prepare an isolated Python 3.11 runtime, then launch the local app.

Checks do not import the app, read .env, initialize models, or call Gemini.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import subprocess
import sys
import time
import uuid

BACKEND_DIR = Path(__file__).resolve().parent
REQUIRED_DISTRIBUTIONS = (
    "flask", "flask-cors", "requests", "httpx", "python-dotenv", "pyyaml",
    "numpy", "rank-bm25", "nltk", "sentence-transformers", "torch",
    "google-genai", "pymongo", "openai-whisper", "edge-tts",
)
PYTHON_PROBE = (
    "import json,struct,sys; "
    "print(json.dumps({'version':list(sys.version_info[:2]),"
    "'bits':struct.calcsize('P')*8,'prefix':sys.prefix}))"
)
IMPORT_PROBE = (
    "import flask,flask_cors,requests,httpx,dotenv,yaml,numpy,rank_bm25,nltk; "
    "import torch,sentence_transformers,pymongo,edge_tts; "
    "from google import genai; print('Runtime imports passed.')"
)
NLTK_SETUP = """
import nltk,sys
from pathlib import Path
destination=Path(sys.argv[1])
check_only=sys.argv[2]=='check'
nltk.data.path.insert(0,str(destination))
resources=(('punkt','tokenizers/punkt'),('punkt_tab','tokenizers/punkt_tab'),('stopwords','corpora/stopwords'))
for package,resource in resources:
    try:
        nltk.data.find(resource,paths=[str(destination)])
    except LookupError:
        if check_only:
            raise SystemExit('Missing local NLTK resource '+package+'. Run start_fiqhbot.cmd --setup-only.')
        destination.mkdir(parents=True,exist_ok=True)
        if not nltk.download(package,download_dir=str(destination),quiet=True):
            raise SystemExit('Could not download NLTK resource '+package+'. Retry setup with internet access.')
        nltk.data.find(resource,paths=[str(destination)])
print('Local NLTK resources are ready.')
"""


class SetupError(Exception):
    """An actionable local setup failure."""


@contextmanager
def setup_lock(backend):
    """A second launcher must not rebuild/install into the same environment."""
    cache = backend / ".cache"
    cache.mkdir(exist_ok=True)
    with (cache / "setup.lock").open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if not handle.tell():
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise SetupError("Another FIQHBOT launcher is checking/installing dependencies. Wait for it to finish, then retry.") from error
        yield


def python_is_usable(executable, *, expected_prefix=None):
    try:
        result = subprocess.run(
            [str(executable), "-I", "-B", "-c", PYTHON_PROBE],
            capture_output=True, text=True, timeout=10,
        )
        details = json.loads(result.stdout)
        return (result.returncode == 0 and details["version"] == [3, 11]
                and details["bits"] == 64
                and (expected_prefix is None
                     or Path(details["prefix"]).resolve() == expected_prefix.resolve()))
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
        return False


def run_checked(command, *, cwd, timeout=None):
    try:
        result = subprocess.run([str(part) for part in command], cwd=cwd, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        raise SetupError("Runtime check timed out; the app was not started.") from error
    except OSError as error:
        raise SetupError("Could not run the selected Python interpreter.") from error
    if result.returncode:
        raise SetupError("Setup/check failed. Resolve the error above, then run the launcher again.")


def preserve_broken_environment(environment):
    """Rename only this backend's venv; never delete its installed packages."""
    if environment.parent.resolve() != BACKEND_DIR.resolve() or environment.name != "venv":
        raise SetupError("Refusing to move an environment outside this backend.")
    attributes = environment.lstat()
    if environment.is_symlink() or (getattr(attributes, "st_file_attributes", 0)
                                   & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)):
        raise SetupError("backend/venv is a link. Replace it with a local environment before setup.")
    backup = environment.with_name("venv.backup-" + time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6])
    environment.rename(backup)
    print("Previous environment preserved as " + backup.name, flush=True)
    return backup


def check_dependencies(python, backend, *, imports=False):
    probe = (
        "import importlib.metadata as m,sys; "
        "installed={d.metadata['Name'].lower().replace('_','-') for d in m.distributions()}; "
        "missing=set(" + repr(REQUIRED_DISTRIBUTIONS) + ")-installed; "
        "print('Missing packages: '+', '.join(sorted(missing))) if missing else None; "
        "sys.exit(bool(missing))"
    )
    run_checked([python, "-I", "-B", "-c", probe], cwd=backend, timeout=30)
    run_checked([python, "-I", "-B", "-m", "pip", "check"], cwd=backend, timeout=30)
    run_checked([python, "-I", "-B", "-m", "pip", "--isolated", "--disable-pip-version-check",
                 "install", "--dry-run", "--no-index", "--no-deps", "--no-cache-dir", "--quiet",
                 "-r", backend / "requirements.txt"], cwd=backend, timeout=30)
    if imports:
        run_checked([python, "-I", "-B", "-c", IMPORT_PROBE], cwd=backend, timeout=120)


def prepare_nltk(python, backend, *, check_only=False):
    run_checked([python, "-I", "-B", "-c", NLTK_SETUP, backend / ".cache" / "nltk_data",
                 "check" if check_only else "setup"], cwd=backend, timeout=180)


def prepare_environment(backend=BACKEND_DIR, *, check_only=False):
    environment = backend / "venv"
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    requirements = backend / "requirements.txt"
    marker = environment / ".fiqhbot-requirements.sha256"
    digest = hashlib.sha256(requirements.read_bytes()).hexdigest()
    usable = python_is_usable(python, expected_prefix=environment)
    if check_only:
        if not usable:
            raise SetupError("backend/venv cannot run Python 3.11 (64-bit). Run start_fiqhbot.cmd --setup-only to rebuild it.")
        check_dependencies(python, backend, imports=True)
        prepare_nltk(python, backend, check_only=True)
        print("Local Python runtime is ready. Models and Gemini have not been checked.", flush=True)
        return python

    if not usable:
        if environment.exists() or environment.is_symlink():
            preserve_broken_environment(environment)
        print("Creating a clean Python 3.11 environment...", flush=True)
        run_checked([sys.executable, "-I", "-B", "-m", "venv", environment], cwd=backend, timeout=120)
        if not python_is_usable(python, expected_prefix=environment):
            raise SetupError("The new environment could not run Python 3.11 (64-bit).")

    needs_install = not marker.is_file() or marker.read_text(encoding="ascii").strip() != digest
    if not needs_install:
        try:
            check_dependencies(python, backend)
        except SetupError:
            needs_install = True
    if needs_install:
        print("Installing/checking FIQHBOT dependencies. Internet is needed for missing packages...", flush=True)
        run_checked([python, "-I", "-B", "-m", "ensurepip", "--upgrade"], cwd=backend, timeout=120)
        run_checked([python, "-I", "-B", "-m", "pip", "install", "--disable-pip-version-check",
                     "-r", requirements], cwd=backend)
        check_dependencies(python, backend, imports=True)
    prepare_nltk(python, backend)
    if needs_install:
        marker.write_text(digest + "\n", encoding="ascii")
    return python


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--setup-only", action="store_true", help="prepare dependencies without starting the app")
    action.add_argument("--check", action="store_true", help="check Python/packages without installing or starting the app")
    parser.add_argument("--no-browser", action="store_true", help="start the local app without opening a browser")
    args = parser.parse_args(argv)
    try:
        if sys.version_info[:2] != (3, 11) or struct.calcsize("P") != 8:
            raise SetupError("FIQHBOT requires Python 3.11 (64-bit). Set FIQHBOT_PYTHON to its python.exe path.")
        if not (args.check or args.setup_only) and not ((BACKEND_DIR / ".env").is_file()
                                                     or os.environ.get("GEMINI_API_KEY", "").strip()):
            raise SetupError("Copy backend/.env.example to backend/.env and configure GEMINI_API_KEY before starting.")
        if args.check:
            python = prepare_environment(check_only=True)
        else:
            with setup_lock(BACKEND_DIR):
                python = prepare_environment()
        if args.check or args.setup_only:
            return 0
        command = [str(python), "-B", "-u", str(BACKEND_DIR / "start_local.py")]
        if args.no_browser:
            command.append("--no-browser")
        return subprocess.call(command, cwd=BACKEND_DIR)
    except (SetupError, OSError) as error:
        print("FIQHBOT: " + str(error), file=sys.stderr, flush=True)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
