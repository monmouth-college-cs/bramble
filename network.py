#!/usr/bin/env python3
from config import *
import time, sys, os
from fabric import Connection
from fabric import ThreadingGroup

switch_type = "poe-gigabit"
server_ip = '10.40.42.7'
cxn_args = {'password': 'raspberry'}
server = Connection(server_ip, user='pi', connect_kwargs=cxn_args)
local_output_dir = "./output/network"
remote_output_dir = "/home/pi/experiments/network"
niter = 5

## Create directory to gather in
def setup(group):
    os.makedirs(local_output_dir, exist_ok=True)
    for c in group:
        c.run(f"mkdir -p {remote_output_dir}")
        c.run(f"rm -rf {remote_output_dir}/*")

def gather_all2one_results(clients, server):
    desc = f"all2one-{switch_type}"
    for i,c in enumerate(clients):
        c.get(f"{remote_output_dir}/client.log", f"{local_output_dir}/client-{i+1}-{desc}.log")
    server.get(f"{remote_output_dir}/server.log", f"{local_output_dir}/server-{desc}.log")

def gather_one2all_results(client, servers):
    desc = f"one2all-{switch_type}"
    for i,c in enumerate(servers):
        c.get(f"{remote_output_dir}/server.log", f"{local_output_dir}/server-{i+1}-{desc}.log")
    for i in range(len(servers)):
        client.get(f"{remote_output_dir}/client-to-s{i+1}.log", f"{local_output_dir}/client-to-s{i+1}-{desc}.log")
        
# N-1 clients to 1 server
def run_all2one(bramble, server_ip, niter=niter):
    server = Connection(server_ip, user='pi', connect_kwargs=cxn_args)
    ips = [c.host for c in bramble if c.host != server_ip]
    clients = ThreadingGroup(*ips, user='pi', connect_kwargs=cxn_args)
    print(f"Begin {len(clients)} clients to 1 server experiment")

    server.run("killall -q iperf", warn=True)
    time.sleep(10) # wait for old process to die
    server.run(f"iperf -s > {remote_output_dir}/server.log &")

    for i in range(niter):
        print(f"Iteration {i}")
        clients.run("killall -q iperf", warn=True)
        time.sleep(10) # wait for processes to die
        clients.run(f"iperf -P 20 -c {server.host} >> {remote_output_dir}/client.log")

    gather_all2one_results(clients, server)

# 1 client to N-1 servers
def run_one2all(bramble, client_ip, niter=niter):
    client = Connection(client_ip, user='pi', connect_kwargs=cxn_args)
    ips = [c.host for c in bramble if c.host != client_ip]
    servers = ThreadingGroup(*ips, user='pi', connect_kwargs=cxn_args)
    print(f"Begin 1 client to {len(servers)} servers experiment")

    for c in servers:
        c.run("killall -q iperf", warn=True)
        time.sleep(10) # wait for old process to die
        c.run(f"iperf -s > {remote_output_dir}/server.log &")

    # I'm just *creating* the command here, not running it yet
    ips = [c.host for c in servers]
    cmds = [f"(iperf -P 2 -c {s} >> {remote_output_dir}/client-to-s{i+1}.log &)" for i,s in enumerate(ips)]
    cmd = ';'.join(cmds)

    print("one2all command string: ", cmd)

    for i in range(niter):
        print(f"Iteration {i}")
        client.run("killall -q iperf", warn=True)
        time.sleep(10) # wait for the processes to die
        client.run(cmd)

    gather_one2all_results(client, servers)
    
with open('hosts.txt') as f:
    ips = [line.strip() for line in f]

bramble = ThreadingGroup(*ips, user='pi', connect_kwargs=cxn_args)
setup(bramble)
run_all2one(bramble, server_ip)
run_one2all(bramble, server_ip)


