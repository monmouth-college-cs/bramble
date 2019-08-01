#!/usr/bin/env python3
import sys, os
from fabric import Connection
from fabric import SerialGroup as Group
from paramiko.ssh_exception import AuthenticationException

# Parameters
hostname_prefix = 'bramble-pi'
ip3 = '42' # ip addresses will be "x.x.{ip3}.{num}"

def file_append(cxn, filepath, data, use_sudo=False):
  cmd = f"tee -a {filepath} <<EOF \n{data}\nEOF"
  func = cxn.sudo if use_sudo else cxn.run
  func(cmd, hide='out')

def reboot(cxn):
  cxn.sudo('reboot', warn=True)

def sudoput(cxn, local_path, remote_path):
  cxn.put(local_path, remote='/tmp/sudoput')
  cxn.sudo(f"mv /tmp/sudoput {remote_path}")

def keygen(cxn):
  # @TODO: Remove this file if it already exists
  cxn.run("mkdir -p ~/.ssh")
  cxn.run('ssh-keygen -f ~/.ssh/id_rsa -t rsa -q -N ""')

# Note that a restart is required after this!
def set_static_ip(cxn, router, ip_addr):
  # Move over the default /etc/dhcpcd.conf file
  sudoput(cxn, './data/dhcpcd.conf', '/etc/dhcpcd.conf')

  config_txt = f"""
interface eth0
static ip_address={ip_addr}/24
static routers={router}
static domain_name_servers={router} 8.8.8.8"""
  #cxn.sudo(f"cat >>/etc/dhcpcd.conf <<EOF \n{config_txt}\nEOF")
  file_append(cxn, '/etc/dhcpcd.conf', config_txt, use_sudo=True)
  print(f"{cxn.host} --> {ip_addr}")

def set_hostname(cxn, hostname):
  cxn.sudo(f"raspi-config nonint do_hostname {hostname}", hide='both')

def setup_hostsfile(cxn, data):
  header, footer = "Bramble Begin", "Bramble End"
  data = f"\n# {header}\n" + data + f"\n# {footer}\n"

  # Delete if already there
  cxn.sudo(f"sed -i '/{header}/,/{footer}/d' /etc/hosts")
  file_append(cxn, '/etc/hosts', data, use_sudo=True)

def config_cluster_network(group, router, ip_prefix, hostfile_data, local_keyfile):
  os.makedirs('./keyfiles', exist_ok=True)
  for i,c in enumerate(group):
    hostname = f"{hostname_prefix}{i+1}"
    set_static_ip(c, router, f"{ip_prefix}.{i+1}")
    set_hostname(c, hostname)
    setup_hostsfile(c, hostfile_data)
    keygen(c)
    c.get('/home/pi/.ssh/id_rsa.pub', f"./keyfiles/{hostname}.pub")

    # TODO: concatenate alltogether into one file
    # TODO: Copy file to each pi as authorized keys
    reboot(c)

def main():
  with open('initial_hosts.txt') as f:
    ips = [line.strip() for line in f]

  cxn_args = {'password': 'raspberry'}
  bramble = Group(*ips, user='pi', connect_kwargs=cxn_args)

  router = bramble[0].run("ip route | grep default | awk '{print $3}'", hide='both').stdout.strip()
  print(f"Router IP: {router}")

  ip_prefix = '.'.join(router.split('.')[:2]) + f".{ip3}"
  lines = [f"{ip_prefix}.{i+1}     {hostname_prefix}{i+1}" for i in range(len(bramble))]
  lines.insert(0, '# Bramble')
  lines.insert(0, '')
  hostfile_data = '\n'.join(lines)

  local_keyfile = None if len(sys.argv) == 1 else sys.argv[1]

  config_cluster_network(bramble, router, ip_prefix, hostfile_data, local_keyfile)

if __name__ == "__main__":
  main()

def setup_nfs_client(cxn):
  cxn.sudo('apt install nfs-common')

# Optional argument is local filename of public key to use
# Should not require a passphrase!
# def setup_ssh_keys(cxn, filename=None):
#   if filename != None:


#bramble.run('hostname', hide='both')

#c = Connection(ips[0], user='pi',

# When calling 'run', use hide='{out,err,both}' to hide the normal output
# Access with result.stdout,e tc.
# Similarly, use warn=True to continue instead of raising UnexpectedExit

# try:
#   c.run('hostname')
# except AuthenticationException:
#   print("Authentication Failure!")
#   sys.exit(1)

# Get results from running
# result = c.run('blah')
# result.stdout.strip() or stderr

# Transfer files:
#res = c.put('localfilename' remote='remotefilename')
# res.local, res.remote show filenames
