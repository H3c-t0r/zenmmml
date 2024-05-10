#!/bin/bash

DB="sqlite"
DB_STARTUP_DELAY=30 # Time in seconds to wait for the database container to start

export ZENML_ANALYTICS_OPT_IN=false
export ZENML_DEBUG=true

# Use a temporary directory for the config path
export ZENML_CONFIG_PATH=/tmp/upgrade-tests

if [ -z "$1" ]; then
  echo "No argument passed, using default: $DB"
else
  DB="$1"
fi

# List of versions to test
VERSIONS=("0.55.2" "0.56.4")

# Function to compare semantic versions
function version_compare() {
    local regex="^([0-9]+)\.([0-9]+)\.([0-9]+)(-([0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*))?(\\+([0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*))?$"
    local ver1="$1"
    local ver2="$2"

    if [[ "$ver1" == "$ver2" ]]; then
        echo "="
        return
    fi

    if [[ $ver1 == "current" ]]; then
        echo ">"
        return
    fi

    if [[ $ver2 == "current" ]]; then
        echo "<"
        return
    fi

    if ! [[ $ver1 =~ $regex ]]; then
        echo "First argument does not conform to semantic version format" >&2
        return 1
    fi

    if ! [[ $ver2 =~ $regex ]]; then
        echo "Second argument does not conform to semantic version format" >&2
        return 1
    fi

    # Compare major, minor, and patch versions
    IFS='.' read -ra ver1_parts <<< "$ver1"
    IFS='.' read -ra ver2_parts <<< "$ver2"

    for ((i=0; i<3; i++)); do
        if ((ver1_parts[i] > ver2_parts[i])); then
            echo ">"
            return
        elif ((ver1_parts[i] < ver2_parts[i])); then
            echo "<"
            return
        fi
    done

    # Extend comparison to pre-release versions if necessary
    # This is a simplified comparison that may need further refinement
    if [[ -n ${ver1_parts[3]} && -z ${ver2_parts[3]} ]]; then
        echo "<"
        return
    elif [[ -z ${ver1_parts[3]} && -n ${ver2_parts[3]} ]]; then
        echo ">"
        return
    elif [[ -n ${ver1_parts[3]} && -n ${ver2_parts[3]} ]]; then
        if [[ ${ver1_parts[3]} > ${ver2_parts[3]} ]]; then
            echo ">"
            return
        elif [[ ${ver1_parts[3]} < ${ver2_parts[3]} ]]; then
            echo "<"
            return
        fi
    fi

    echo "="
}

function run_tests_for_version() {
    set -e  # Exit immediately if a command exits with a non-zero status
    local VERSION=$1

    echo "===== Testing version $VERSION ====="

    rm -rf test_starter template-starter

    # Check if the version supports templates via zenml init (> 0.43.0)
    if [ "$(version_compare "$VERSION" "0.43.0")" == ">" ]; then
        mkdir test_starter
        zenml init --template starter --path test_starter --template-with-defaults <<< $'my@mail.com\n'
    else
        copier copy -l --trust -r release/0.43.0 https://github.com/zenml-io/template-starter.git test_starter
    fi

    cd test_starter

    echo "===== Installing sklearn integration ====="
    zenml integration export-requirements sklearn --output-file sklearn-requirements.txt
    uv pip install -r sklearn-requirements.txt
    rm sklearn-requirements.txt

    echo "===== Running starter template pipeline ====="
    # Check if the version supports templates with arguments (> 0.52.0)
    if [ "$(version_compare "$VERSION" "0.52.0")" == ">" ]; then
        python3 run.py --feature-pipeline --training-pipeline --no-cache
    else
        python3 run.py --no-cache
    fi
    # Add additional CLI tests here
    zenml version

    # Confirm DB works and is accessible
    pipelines=$(ZENML_LOGGING_VERBOSITY=INFO zenml pipeline runs list)
    echo "$pipelines"

    # The database backup and restore feature is available since 0.55.1.
    # However, it has been broken for various reasons up to and including
    # 0.56.3, so we skip this test for those versions.
    if [ "$VERSION" == "current" ] || [ "$(version_compare "$VERSION" "0.56.3")" == ">" ]; then
        echo "===== Testing database backup and restore ====="

        # Perform a DB backup and restore using a dump file
        rm -f /tmp/zenml-backup.sql
        zenml backup-database -s dump-file --location /tmp/zenml-backup.sql
        zenml restore-database -s dump-file --location /tmp/zenml-backup.sql

        # Check that DB still works after restore and the content is the same
        pipelines_after_restore=$(ZENML_LOGGING_VERBOSITY=INFO zenml pipeline runs list)
        if [ "$pipelines" != "$pipelines_after_restore" ]; then
            echo "----- Before restore -----"
            echo "$pipelines"
            echo "----- After restore -----"
            echo "$pipelines_after_restore"
            echo "ERROR: database backup and restore test failed!"
            exit 1
        fi

        # For a mysql compatible database, perform a DB backup and restore using
        # the backup database
        if [ "$DB" == "mysql" ] || [ "$DB" == "mariadb" ]; then
            # Perform a DB backup and restore
            zenml backup-database -s database --location zenml-backup
            zenml restore-database -s database --location zenml-backup

            # Check that DB still works after restore and the content is the
            # same
            pipelines_after_restore=$(ZENML_LOGGING_VERBOSITY=INFO zenml pipeline runs list)
            if [ "$pipelines" != "$pipelines_after_restore" ]; then
                echo "----- Before restore -----"
                echo "$pipelines"
                echo "----- After restore -----"
                echo "$pipelines_after_restore"
                echo "ERROR: database backup and restore test failed!"
                exit 1
            fi
        fi
    else
        echo "Skipping database backup and restore test for version $VERSION"
    fi

    cd ..
    rm -rf test_starter template-starter
    echo "===== Finished testing version $VERSION ====="
}

function test_upgrade_to_version() {
    set -e  # Exit immediately if a command exits with a non-zero status
    local VERSION=$1

    echo "===== Testing upgrade to version $VERSION ====="

    # (re)create a virtual environment
    rm -rf ".venv-upgrade"
    uv venv ".venv-upgrade"
    source ".venv-upgrade/bin/activate"

    # Install the specific version
    uv pip install -U setuptools wheel pip

    if [ "$VERSION" == "current" ]; then
        uv pip install -e ".[templates,server]"
    else
        uv pip install "zenml[templates,server]==$VERSION"
        # handles unpinned sqlmodel dependency in older versions
        uv pip install "sqlmodel==0.0.8" "bcrypt==4.0.1" "pyyaml-include<2.0"
    fi

    # Get the major and minor version of Python
    PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')

    # Check if the Python version is 3.9 and VERSION is > 0.44.0 and < 0.53.0
    if [[ "$PYTHON_VERSION" == "3.9" ]]; then
        if [ "$(version_compare "$VERSION" "0.44.0")" == ">" ] && [ "$(version_compare "$VERSION" "0.53.0")" == "<" ]; then
            # Install importlib_metadata for Python 3.9 and versions > 0.44.0 and < 0.53.0
            uv pip install importlib_metadata
        fi
    fi

    if [ "$DB" == "mysql" ] || [ "$DB" == "mariadb" ]; then
                zenml connect --url mysql://127.0.0.1/zenml --username root --password password
    fi

    # Run the tests for this version
    run_tests_for_version "$VERSION"

    deactivate
    rm -rf ".venv-upgrade"

    echo "===== Finished testing upgrade to version $VERSION ====="
}

function start_db() {
    set -e  # Exit immediately if a command exits with a non-zero status

    if [ "$DB" == "sqlite" ]; then
        return
    fi

    stop_db    

    echo "===== Starting $DB database ====="
    if [ "$DB" == "mysql" ]; then
        # run a mysql instance in docker
        docker run --name mysql --rm -d -p 3306:3306 -e MYSQL_ROOT_PASSWORD=password mysql:8
    elif [ "$DB" == "mariadb" ]; then
        # run a mariadb instance in docker
        docker run --name mariadb --rm -d -p 3306:3306 -e MYSQL_ROOT_PASSWORD=password mariadb:10.6
    fi

    # the database container takes a while to start up
    sleep $DB_STARTUP_DELAY
    echo "===== Finished starting $DB database ====="

}

function stop_db() {
    set -e  # Exit immediately if a command exits with a non-zero status

    if [ "$DB" == "sqlite" ]; then
        return
    fi

    echo "===== Stopping $DB database ====="

    if [ "$DB" == "mysql" ]; then
        docker stop mysql || true
    elif [ "$DB" == "mariadb" ]; then
        docker stop mariadb || true
    fi

    echo "===== Finished stopping $DB database ====="
}

# If testing the mariadb database, we remove versions older than 0.54.0 because
# we only started supporting mariadb from that version onwards
if [ "$DB" == "mariadb" ]; then
    MARIADB_VERSIONS=()
    for VERSION in "${VERSIONS[@]}"
    do
        if [ "$(version_compare "$VERSION" "0.54.0")" == "<" ]; then
            continue
        fi
        MARIADB_VERSIONS+=("$VERSION")
    done
    VERSIONS=("${MARIADB_VERSIONS[@]}")
fi

echo "Testing database: $DB"
echo "Testing versions: ${VERSIONS[@]}"

# Start completely fresh
rm -rf "$ZENML_CONFIG_PATH"

pip install -U uv

# Start the database
start_db

for VERSION in "${VERSIONS[@]}"
do
    test_upgrade_to_version "$VERSION"
done

# Test the most recent migration with MySQL
test_upgrade_to_version "current"


# Start fresh again for this part
rm -rf "$ZENML_CONFIG_PATH"

# fresh database for sequential testing
stop_db

# Clean up
rm -rf "$ZENML_CONFIG_PATH"
