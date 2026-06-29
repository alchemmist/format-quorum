#!/usr/bin/env bash
set -euo pipefail

name=${1:-world}
greet(){ echo "hello, $1"; }

for i in 1 2 3;do greet "$name-$i";done

if [ -f /etc/hostname ];then host=$(cat /etc/hostname);else host=unknown;fi

case "$host" in
prod*) echo "production";;
*) echo "other: $host";;
esac
