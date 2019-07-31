#!/bin/bash
set -e
sudo nmap -n -sP 10.40.20.* | egrep -i 'dc:a6:32|b8:27:eb' -B2 | egrep -o '[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$'
