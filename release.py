#!/usr/bin/env python3

import tomlkit
import argparse
import logging
from git import Repo, GitCommandError

DEFAULT_PYPROJECT_TOML = "pyproject.toml"
DEFAULT_VERSION_TXT = "version.txt"


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def get_module_name(file_path):
    try:
        with open(file=file_path) as file:
            data = tomlkit.load(file)
            if "tool" in data and "poetry" in data["tool"]:
                return data["tool"]["poetry"]["name"]
    except Exception as e:
        logger.exception(f"Failed to locate module name in {file_path}: {e}")
        raise


def update_version_in_pyproject(file_path, new_version):
    """Update the version in the pyproject.toml file."""
    try:
        with open(file=file_path) as file:
            data = tomlkit.load(file)
            if "tool" in data and "poetry" in data["tool"]:
                data["tool"]["poetry"]["version"] = new_version
            else:
                raise ValueError(
                    "The 'version' key under '[tool.poetry]' is not found in the TOML file."
                )

        with open(file_path, "w") as file:
            tomlkit.dump(data, file)
        logger.info(f"Updated version to {new_version} in {file_path}")
    except Exception as e:
        logger.exception(f"Failed to update version in {file_path}: {e}")
        raise


def update_version_in_versiontxt(file_path, new_version):
    """Update the version in the version.txt file."""
    try:
        with open(file_path, "w") as file:
            file.write(new_version)
        logger.info(f"Updated version to {new_version} in {file_path}")
    except Exception as e:
        logger.exception(f"Failed to update version in {file_path}: {e}")
        raise


def commit_and_tag(repo, paths, new_version):
    """Commit the version change and tag the commit."""
    try:
        # Stage the files
        for file_path in paths:
            repo.git.add(file_path)
            logger.info(f"Staged file: {file_path}")

        # Commit the change
        commit_message = f"release: increment version to {new_version}"
        repo.index.commit(commit_message)
        logger.info(f"Committed changes: {commit_message}")

        # Create and push a new tag
        repo.create_tag(new_version, message=new_version)
        logger.info(f"Created Git tag: {new_version}")

        # Push the changes and the tag
        origin = repo.remote(name="origin")
        origin.push()
        origin.push(new_version)
        logger.info(f"Pushed changes and tag: {new_version}")
    except Exception as e:
        logger.exception(f"Failed to commit or tag changes: {e}")
        raise


def release_version(repo, pyproject_toml, version_txt, new_version):
    update_version_in_pyproject(pyproject_toml, new_version)
    update_version_in_versiontxt(file_path=version_txt, new_version=new_version)
    commit_and_tag(repo, [pyproject_toml, version_txt], new_version)


def rollback_version(repo, pyproject_path, versiontxt_path, previous_version, current_version):
    """Rollback the version by deleting the tag and restoring the version."""
    try:
        # Delete the remote tag
        origin = repo.remote(name="origin")
        origin.push(refspec=f":refs/tags/{current_version}")
        logger.info(f"Deleted remote tag: {current_version}")

        # Delete the local tag
        repo.delete_tag(current_version)
        logger.info(f"Deleted local tag: {current_version}")

        # Restore the version in pyproject.toml
        update_version_in_pyproject(file_path=pyproject_path, new_version=previous_version)

        # Restore the version in pyproject.toml
        update_version_in_versiontxt(file_path=versiontxt_path, new_version=previous_version)

        # Commit the rollback
        repo.git.add(pyproject_path)
        repo.git.add(versiontxt_path)
        commit_message = f"release: rollback to version {previous_version}"
        repo.index.commit(commit_message)
        logger.info(f"Committed rollback: {commit_message}")

        # Push the rollback commit
        origin.push()
        logger.info("Pushed rollback commit to remote.")
    except GitCommandError as e:
        logger.exception(f"Git command failed: {e}")
        raise
    except Exception as e:
        logger.exception(f"Rollback failed: {e}")
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Manage the version in pyproject.toml and Git tags."
    )
    parser.add_argument(
        "--pyproject_toml",
        default=DEFAULT_PYPROJECT_TOML,
        help=f"The path to the pyproject.toml file (default: {DEFAULT_PYPROJECT_TOML})",
    )

    parser.add_argument(
        "--version_txt",
        default=DEFAULT_VERSION_TXT,
        help=f"The name of the version.txt file. Assumed to be at root of module. (default: {DEFAULT_VERSION_TXT})",
    )

    parser.add_argument(
        "--push",
        action="store_true",
        default=False,
        help="Push changes (default: false)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: release
    release_parser = subparsers.add_parser(
        "release", help="Release a new version and create a Git tag."
    )
    release_parser.add_argument("version", help="The new version to set in pyproject.toml")

    # Subcommand: rollback
    rollback_parser = subparsers.add_parser("rollback", help="Rollback to a previous version.")
    rollback_parser.add_argument("previous_version", help="The previous version to restore.")
    rollback_parser.add_argument("current_version", help="The current version to rollback from.")

    args = parser.parse_args()

    pyproject_toml = args.pyproject_toml
    version_txt = args.version_txt

    module_name = get_module_name(pyproject_toml)
    version_txt_path = f'{module_name}/{version_txt}'

    try:
        # Detect Git repository
        repo = Repo(".")
        if not repo.bare:
            logger.info("Git repository detected.")
        else:
            raise Exception("No Git repository found in the current directory.")

        if args.command == "release":
            release_version(repo, pyproject_toml, version_txt_path, args.version)
        elif args.command == "rollback":
            rollback_version(
                repo=repo,
                pyproject_path=pyproject_toml,
                versiontxt_path=version_txt_path,
                previous_version=args.previous_version,
                current_version=args.current_version,
            )
    except Exception as e:
        logger.critical(f"Script failed: {e}")


if __name__ == "__main__":
    main()
