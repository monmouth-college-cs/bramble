#!/usr/bin/env python3
from config import *
import time, sys, os
from fabric import Connection
from fabric import ThreadingGroup
import pexpect

cooltype="none"

reboot_wait_time = 5*60
exp_dir = "/home/pi/"
exp_script = exp_dir + "thermal.sh"
output_dir = "./output/thermal"

with open('hosts.txt') as f:
    ips = [line.strip() for line in f]

cxn_args = {'password': 'raspberry'}
bramble = ThreadingGroup(*ips, user='pi', connect_kwargs=cxn_args)

def one_time_setup(group):
    os.makedirs(output_dir, exist_ok=True)
    for c in group:
        install(c, 'sysbench')
        setup_firmware(c)

# Careful with this. I still get occassional errors where a Pi won't
# restart -- either hanging before restart or doesn't boot correctly,
# or doesn't get correct IP address. I don't have the time to debug
# it.
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

def setup_run(group):
    for c in group:
        c.run(f"rm -f {exp_script}")
        c.put("./thermal.sh", remote=exp_script)
        c.run("rm -f *.log")

def run(group, fw):
    #prepare(group, fw)
    setup_run(group)
    for c in group:
        actual_fw = get_firmware(c)
        assert actual_fw == fw
        print(f"[{c.host}] Preparing to run {exp_script} {fw} {cooltype}")
    group.run(f"{exp_script} {fw} {cooltype}", hide='both')

def gather_results(group):
    for c in group:
        # Fabric is stupid and can't handle this, even though the documentation says it can.
        # c.get("*.log", "./output/")
        # TODO: write helper function that can actually handle it
        # For now you'll have to manually input the Pi's password when it asks for it
        #os.system(f"scp pi@{c.host}:/home/pi/*.log {output_dir}/")
        cmd = f"scp pi@{c.host}:/home/pi/*.log {output_dir}/"
        print(f"Gathering results: {cmd}")
        child = pexpect.spawn(cmd)
        res = child.expect('pi.* password:')
        assert res == 0
        res = child.sendline('raspberry')
        child.expect(pexpect.EOF)

test_connections(bramble)
one_time_setup(bramble)

# I originally set up this script to test both old firmware and
# new. Unfortunately, there seems to be a bug (unconfirmed, but I'm
# 99% sure) when you are currently using the new firmware and try to
# switch to the old firmware. When you try to restart it will hang,
# saying something about "stopping restore" and "save the current
# clock". You'd have to manually cycle the power to actually
# restart. So, we will just test the new firmware...

## run(bramble, oldfw)

run(bramble, newfw)
gather_results(bramble)
