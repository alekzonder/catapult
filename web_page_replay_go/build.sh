#!/bin/bash

# https://github.com/mitchellh/gox
gox -osarch="darwin/amd64" -osarch="linux/amd64" ./src

rm wpr-darwin.tgz wpr-linux.tgz


# darwin
rm -rf ./wpr
mkdir -p ./wpr
mv src_darwin_amd64 ./wpr/wpr
cp wpr_cert.pem ./wpr/
cp wpr_key.pem ./wpr/
cp deterministic.js ./wpr/

echo 'build and copied from catapult project for Macos (darwin)' > ./wpr/README.md
echo 'see https://github.com/alekzonder/catapult/tree/custom/web_page_replay_go' >> ./wpr/README.md

tar czf ./wpr-darwin.tgz ./wpr


# linux

rm -rf ./wpr
mkdir -p ./wpr
mv src_linux_amd64 ./wpr/wpr
cp wpr_cert.pem ./wpr/
cp wpr_key.pem ./wpr/
cp deterministic.js ./wpr/

echo 'build and copied from catapult project for linux (linux)' > ./wpr/README.md
echo 'see https://github.com/alekzonder/catapult/tree/custom/web_page_replay_go' >> ./wpr/README.md

tar czf ./wpr-linux.tgz ./wpr