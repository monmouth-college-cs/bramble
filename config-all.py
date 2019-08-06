#!/usr/bin/env python3
import sys, os, glob, time
from fabric import Connection
from fabric import SerialGroup as Group
from paramiko.ssh_exception import AuthenticationException

# Parameters
hostname_prefix = 'bramble-pi'
ip3 = '43' # ip addresses will be "x.x.{ip3}.{num}"
nfs_dir = '/export/nfs'

# Governor options:
#  performance: max frequency, no throttling
#  powersave: min frequency, no throtting
#  ondemand: throttle frequency based on load
# There are others, but I don't think we'll need them.
def set_freq_scaling(cxn, governor):
  file_write(cxn, '/sys/devices/system/cpu/cpu*/cpufreq/scaling_governor',
             governor, append=False, use_sudo=True)

def service_cmd(cxn, service, cmd):
  cxn.sudo(f"systemctl {cmd} {service}")

def install(cxn, *pkg):
  cxn.sudo(f"apt install {' '.join(pkg)} -y", hide='out')

def file_write(cxn, filepath, data, append=True, use_sudo=False):
  flags = "-a" if append else ""
  cmd = f"tee {flags} {filepath} <<EOF \n{data}\nEOF"
  func = cxn.sudo if use_sudo else cxn.run
  func(cmd, hide='out')

def reboot(cxn):
  cxn.sudo('reboot', warn=True)

def sudoput(cxn, local_path, remote_path):
  cxn.put(local_path, remote='/tmp/sudoput')
  cxn.sudo(f"mv /tmp/sudoput {remote_path}")

def keygen(cxn):
  cxn.run("mkdir -p ~/.ssh")
  cxn.sudo("chown pi:pi .ssh")
  cxn.sudo("chown pi:pi .ssh/*")
  cxn.run("rm -f ~/.ssh/id_rsa{.pub,}")
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
  file_write(cxn, '/etc/dhcpcd.conf', config_txt, append=True, use_sudo=True)
  print(f"{cxn.host} --> {ip_addr}")

def set_hostname(cxn, hostname):
  cxn.sudo(f"raspi-config nonint do_hostname {hostname}", hide='both')

def setup_hostsfile(cxn, data):
  header, footer = "Bramble Begin", "Bramble End"
  data = f"\n# {header}\n" + data + f"\n# {footer}\n"

  # Delete if already there
  cxn.sudo(f"sed -i '/{header}/,/{footer}/d' /etc/hosts")
  file_write(cxn, '/etc/hosts', data, append=True, use_sudo=True)

def config_cluster_network(group, router, ip_prefix, hostfile_data):
  os.makedirs('./keyfiles', exist_ok=True)
  public_keys = []
  for i,c in enumerate(group):
    hostname = f"{hostname_prefix}{i+1}"
    set_static_ip(c, router, f"{ip_prefix}.{i+1}")
    set_hostname(c, hostname)
    setup_hostsfile(c, hostfile_data)
    keygen(c)
    c.get('/home/pi/.ssh/id_rsa.pub', f"./keyfiles/{hostname}.pub")

    with open("./authorized_keys", 'w') as authorized:
      for keyfile in glob.glob("./keyfiles/*.pub"):
        with open(keyfile) as f:
          authorized.write(f.read())


  for c in group:
    c.put('./authorized_keys', remote='/home/pi/.ssh/authorized_keys')
    reboot(c)

  print("Network configuration done, waiting for reboot.")
  time.sleep(60)

def setup_nfs_client(cxn, master_ip):
  cxn.sudo(f"umount {nfs_dir} || /bin/true")
  cxn.sudo(f"mount {master_ip}:{nfs_dir} {nfs_dir}")

  # Set fstab
  cxn.sudo(f"sed -i '\|^{master_ip}:{nfs_dir}|d' /etc/fstab")
  options="rw,noatime,nodiratime,async"
  line = f"{master_ip}:{nfs_dir} {nfs_dir} nfs {options} 0 0"
  file_write(cxn, '/etc/fstab', line, append=True, use_sudo=True)

def setup_nfs_server(cxn, ip_prefix):
  install(cxn, 'nfs-kernel-server', 'rpcbind')

  # Need to add line in /etc/exports
  # Replace the ip address range with * for open access
  options = "rw,all_squash,insecure,async,no_subtree_check,anonuid=1000,anongid=1000"
  export_line = f"{nfs_dir} {ip_prefix}.0/24({options})"

  # First remove anything similar
  cxn.sudo(f"sed -i '\|^{nfs_dir}|d' /etc/exports")

  # Now add it
  file_write(cxn, '/etc/exports', export_line, append=True, use_sudo=True)

  cxn.sudo('exportfs -ra')
  cxn.run('/sbin/showmount -e localhost')
  service_cmd(cxn, 'rpcbind', 'enable')
  service_cmd(cxn, 'nfs-kernel-server', 'enable')
  service_cmd(cxn, 'nfs-common', 'enable')
  service_cmd(cxn, 'rpcbind', 'start')
  service_cmd(cxn, 'nfs-kernel-server', 'start')
  cxn.sudo('rm -f /lib/systemd/system/nfs-common.service') # "unmask"
  service_cmd(cxn, 'nfs-common', 'start')

def setup_nfs_all(cxn):
  cxn.sudo('apt install nfs-common -y')
  cxn.sudo(f"mkdir -p {nfs_dir}")
  cxn.sudo(f"chown pi:pi {nfs_dir}")
  cxn.sudo(f"chmod 755 {nfs_dir}")

def setup_nfs(group, ip_prefix):
  for c in group:
    setup_nfs_all(c)
  master = group[0]
  setup_nfs_server(master, ip_prefix)
  for c in group[1:]:
    setup_nfs_client(c, master.host)

def main():
  with open('initial_hosts.txt') as f:
    ips = [line.strip() for line in f]

  cxn_args = {'password': 'raspberry'}
  bramble = Group(*ips, user='pi', connect_kwargs=cxn_args)

  router = bramble[0].run("ip route | grep default | awk '{print $3}'", hide='both').stdout.strip()
  print(f"Router IP: {router}")

  ip_prefix = '.'.join(router.split('.')[:2]) + f".{ip3}"
  lines = [f"{ip_prefix}.{i+1}     {hostname_prefix}{i+1}" for i in range(len(ips))]
  lines.insert(0, '# Bramble')
  lines.insert(0, '')
  hostfile_data = '\n'.join(lines)

  config_cluster_network(bramble, router, ip_prefix, hostfile_data)
  new_ips = [f"{ip_prefix}.{i+1}" for i in range(len(ips))]
  bramble = Group(*new_ips, user='pi', connect_kwargs=cxn_args)
  setup_nfs(bramble, ip_prefix)

  for c in bramble:
    reboot(c)

if __name__ == "__main__":
  main()

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
