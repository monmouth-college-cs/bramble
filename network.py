#!/usr/bin/env python3
from config import *
import time, sys, os
from fabric import Connection
from fabric import ThreadingGroup

testtype = "7 clients to 1 server"
server_ip = '10.40.42.7'
cxn_args = {'password': 'raspberry'}
server = Connection(server_ip, user='pi', connect_kwargs=cxn_args)
output_dir = "./output/network"
num_int = 5

with open('hosts.txt') as f:
    ips = [line.strip() for line in f]

ips.remove(server_ip)
clients = ThreadingGroup (*ips, user='pi', connect_kwargs=cxn_args)

##CREATE DIRECTORY TO GATHER IN
def setup(group):
    os.makedirs(output_dir, exist_ok=True)
setup(clients)
##START SERVER_IP

server.run('iperf -s >> server_ip.log&')

##CONNECT TO SERVER_IP

for c in clients:
    c.run("rm -f /home/pi/*.log")

for n in num_int():
    clients.run(f"iperf -P 20 -c {server_ip} >> clients.log")
    

##GATHER LOGS
def gather_results(group):
    for i,c in enumerate(clients):
        c.get("/home/pi/clients.log", f"{output_dir}/networkclient-{i+1}.log")
    server.get("/home/pi/server_ip.log", f"{output_dir}/serverclient.log")
        
gather_results(clients)
