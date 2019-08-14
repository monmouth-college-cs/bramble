#!/usr/bin/env python3
from config import *
import time, sys, os
from fabric import Connection
from fabric import ThreadingGroup

# TODO: problem connecting to pi 7

cooltype="casefan"

reboot_wait_time = 5*60
exp_dir = "/home/pi/"
exp_script = exp_dir + "thermal.sh"
output_dir = "./output/thermal"

with open('hosts.txt') as f:
    ips = [line.strip() for line in f]

cxn_args = {'password': 'raspberry'}
bramble = ThreadingGroup(*ips, user='pi', connect_kwargs=cxn_args)

def setup(group):
    os.makedirs(output_dir, exist_ok=True)
    for c in group:
        setup_firmware(c)
        c.run("rm -f /home/pi/thermal.sh")
        c.put("./thermal.sh", remote='/home/pi/thermal.sh')
        c.run("rm -f *.log")

def prepare(group, fw):
    for c in group:
        set_firmware(c, fw)
        reboot(c)
    print(f"Firmware set to {fw}, waiting {reboot_wait_time//60} minutes for reboot.")
    for t in range(reboot_wait_time, 0, -1):
        print(f"{t:3d} seconds remaining.", end='\r', flush=True)
        time.sleep(1)
    print("Reboot completed." + ' ' * 40, flush=True)
    test_connections(group)

def run(group, fw):
    prepare(group, fw)
    for c in group:
        actual_fw = get_firmware(c)
        assert actual_fw == fw
    print(f"Running {exp_script} {fw} {cooltype}")
    group.run(f"{exp_script} {fw} {cooltype}", hide='both')

def gather_results(group):
    for c in group:
        # Fabric is stupid and can't handle this
        # c.get("*.log", "./output/")
        # TODO: write helper function that can actually handle it
        # For now you'll have to manually input the Pi's password when it asks for it
        os.system(f"scp pi@{c.host}:/home/pi/*.log {output_dir}/")

test_connections(bramble)
setup(bramble)
run(bramble, oldfw)
run(bramble, newfw)
gather_results(bramble)
