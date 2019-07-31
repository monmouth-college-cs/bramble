#!/bin/bash
set -e
sudo nmap -n -sP 10.20.40.* | egrep -i 'dc:a6:32|b8:27:eb' -B2 | egrep -o '10\.10\.[0-9.]+$'
