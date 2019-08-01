#!/bin/bash
set -ex

prefix=${1:-10.40.20} # First argument: IP address prefix

# Second argument: which version Pis to detect
macaddr=""
if [ "$2" = "4" ]; then
    # Just Raspbery Pi 4
    macaddr='dc:a6:32'
elif [ "$2" = "3" ]; then
    # 1, 2, or 3
    macaddr='b8:27:eb'
else
    # Assume all
    macaddr='dc:a6:32|b8:27:eb'
fi
sudo nmap -n -sP ${prefix}.* | egrep -i "$macaddr" -B2 | egrep -o '[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$'
