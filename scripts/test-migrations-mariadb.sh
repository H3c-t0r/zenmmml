#!/bin/bash

DB="mariadb"
DB_STARTUP_DELAY=30 # Time in seconds to wait for the database container to start

function run_tests_for_version() {
    set -e  # Exit immediately if a command exits with a non-zero status
    local VERSION=$1

    echo "===== Testing version $VERSION ====="

    mkdir test_starter
    zenml init --template starter --path test_starter --template-with-defaults --test
    cd test_starter

    export ZENML_ANALYTICS_OPT_IN=false
    export ZENML_DEBUG=true

    echo "===== Installing sklearn integration ====="
    zenml integration export-requirements sklearn --output-file sklearn-requirements.txt
    uv pip install -r sklearn-requirements.txt
    rm sklearn-requirements.txt

    echo "===== Running starter template pipeline ====="
    python3 run.py
    # Add additional CLI tests here
    zenml version

    # Confirm DB works and is accessible
    zenml pipeline runs list

    cd ..
    rm -rf test_starter
    echo "===== Finished testing version $VERSION ====="
}

echo "===== Testing MariaDB ====="

export ZENML_ANALYTICS_OPT_IN=false
export ZENML_DEBUG=true

# run a mariadb instance in docker
docker run --name mariadb -d -p 3306:3306 -e MYSQL_ROOT_PASSWORD=password mariadb:10.6
# mariadb takes a while to start up
sleep $DB_STARTUP_DELAY

# List of versions to test
VERSIONS=("0.54.0" "0.54.1" "0.55.0" "0.55.1" "0.55.2" "0.55.3" "0.55.4" "0.55.5")

# Start completely fresh
rm -rf ~/.config/zenml

pip install -U uv

for VERSION in "${VERSIONS[@]}"
do
    set -e  # Exit immediately if a command exits with a non-zero status
    # Create a new virtual environment
    uv venv ".venv-$VERSION"
    source ".venv-$VERSION/bin/activate"

    # Install the specific version
    uv pip install -U setuptools wheel pip

    git checkout release/$VERSION
    uv pip install -e ".[templates,server]"

    export ZENML_ANALYTICS_OPT_IN=false
    export ZENML_DEBUG=true

    zenml connect --url mysql://127.0.0.1/zenml --username root --password password

    # Run the tests for this version
    run_tests_for_version $VERSION

    zenml disconnect
    sleep 5

    deactivate
done

# Test the most recent migration with MariaDB
echo "===== TESTING CURRENT BRANCH ====="
set -e
uv venv ".venv-current-branch"
source ".venv-current-branch/bin/activate"

uv pip install -U setuptools wheel pip
uv pip install -e ".[templates,server]"
uv pip install importlib_metadata

zenml connect --url mysql://127.0.0.1/zenml --username root --password password

run_tests_for_version current_branch_mariadb

zenml disconnect
docker rm -f mariadb

deactivate
