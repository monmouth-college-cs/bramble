#!/usr/bin/env python3
import sys, os, glob, time, argparse
from fabric import Connection
from fabric import SerialGroup, ThreadingGroup
from paramiko.ssh_exception import AuthenticationException

# Parameters
hostname_prefix = 'bramble-pi'
ip3 = '42' # ip addresses will be "x.x.{ip3}.{num}"
nfs_dir = '/export/nfs'
Group = SerialGroup # Use Serial for debugging
fwdir = '/home/pi/firmware'
oldfw = '013707'
newfw = '0137a8'
base_packages = ['emacs', 'iperf']

# Convenience decorator for functions that require a restart eventually.
def requires_reboot(func):
  def wrapper(*args, **kwargs):
    if 'reboot_now' in kwargs:
      reboot = kwargs.pop('reboot_now')
    else:
      reboot = False # by default, don't reboot
    result = func(*args, **kwargs)
    if reboot:
      reboot(args[0])
    return result
  return wrapper

def raspi_config(cxn, op, value=""):
 cxn.sudo(f"raspi-config nonint {op} {value}")

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
  cxn.sudo(f"apt install {' '.join(pkg)} -y")

def remove(cxn, *pkg):
  cxn.sudo(f"apt remove {' '.join(pkg)} -y")

def setup_mpi(cxn):
  cxn.install(cxn, ['openmpi-common', 'openmpi-bin', 'libopenmpi-dev'])
  cxn.remove(cxn, ['libblas-dev', 'libblas3'])

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

@requires_reboot
def set_static_ip(cxn, router, ip_addr):
  # Move over the default /etc/dhcpcd.conf file
  sudoput(cxn, './data/dhcpcd.conf', '/etc/dhcpcd.conf')

  config_txt = f"""
interface eth0
static ip_address={ip_addr}/24
static routers={router}
static domain_name_servers={router} 8.8.8.8"""
  file_write(cxn, '/etc/dhcpcd.conf', config_txt, append=True, use_sudo=True)
  print(f"{cxn.host} --> {ip_addr}")

@requires_reboot
def set_hostname(cxn, hostname):
  cxn.sudo(f"raspi-config nonint do_hostname {hostname}")

@requires_reboot
def setup_hostsfile(cxn, data):
  header, footer = "Bramble Begin", "Bramble End"
  data = f"\n# {header}\n" + data + f"\n# {footer}\n"

  # Delete if already there
  cxn.sudo(f"sed -i '/{header}/,/{footer}/d' /etc/hosts")
  file_write(cxn, '/etc/hosts', data, append=True, use_sudo=True)

def config_cluster_network(group, router, ip_prefix, reboot_now=False):
  lines = [f"{ip_prefix}.{i+1}     {hostname_prefix}{i+1}" for i in range(len(group))]
  lines = ['# Bramble', *lines, '']
  hostfile_data = '\n'.join(lines)

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
    if reboot_now: reboot(c)

  print("Network configuration done, restart required.")
  if reboot_now:
    print("Waiting 5 minutes for restart.")
    time.sleep(60*5)

def setup_nfs_client(cxn, master_ip):
  cxn.sudo(f"umount -q {nfs_dir}")
  cxn.sudo(f"rm -rf {nfs_dir}")
  cxn.sudo(f"mount {master_ip}:{nfs_dir} {nfs_dir}")

  # Set fstab
  cxn.sudo(f"sed -i '\|{nfs_dir}|d' /etc/fstab")
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

def get_firmware(cxn):
  cxn.sudo(f"{fwdir}/vl805")

@requires_reboot
def set_firmware(cxn, version):
  cxn.sudo(f"{fwdir}/vl805 -w {fwdir}/vl805_fw_{version}.bin")

@requires_reboot
def update_firmware(cxn):
  cxn.run(f"rm -rf {fwdir}")
  cxn.run(f"mkdir -p {fwdir}")
  filename = f"vl805_update_{oldfw}.zip" ##CHANGE TO OLD##
  cxn.put(f"./data/{filename}", remote=f'{fwdir}/{filename}')
  cxn.run(f"cd {fwdir} && unzip {filename} && chmod a+x vl805")
  set_firmware(cxn, oldfw) 
  get_firmware(cxn)

def set_locale(cxn, lang):
  # Unfortunately, this doesn't seem to work, or maybe it requires a reboot.
  raspi_config(cxn, "do_change_locale", lang)

  # So we need to do some extra work...
  header, footer = "# Bramble Config Begin", "# Bramble Config End"

  # Delete if already there
  cxn.sudo(f"sed -i '/{header}/,/{footer}/d' ~/.bashrc")
  file_write(cxn, '~/.bashrc', header, append=True, use_sudo=False)
  for var in ['LANGUAGE', 'LANG', 'LC_ALL']:
    file_write(cxn, '~/.bashrc', f"export {var}={lang}", append=True, use_sudo=False)
  file_write(cxn, '~/.bashrc', footer, append=True, use_sudo=False)
  cxn.run('cat ~/.bashrc')
  cxn.sudo(f"locale-gen {lang}")

@requires_reboot
def initial_config(cxn):
  cxn.sudo("apt update --fix-missing -y")
  cxn.sudo("apt upgrade -y")
  install(cxn, base_packages)
  raspi_config(cxn, "do_expand_rootfs")
  raspi_config(cxn, "do_memory_split", "16") # only use 16MB for GPU
  set_locale(cxn, "en_US.UTF-8")
  raspi_config(cxn, "do_configure_keyboard", "us")
  cxn.sudo("timedatectl set-timezone US/Central") # I don't know how to do this with raspi-config
  update_firmware(cxn)

def get_ip_info(group):
  router = bramble[0].run("ip route | grep default | awk '{print $3}'", hide='both').stdout.strip()
  ip_prefix = '.'.join(router.split('.')[:2]) + f".{ip3}"
  return router, ip_prefix

def main(network, init, nfs, mpi):
  with open('hosts.txt') as f:
    ips = [line.strip() for line in f]
  cxn_args = {'password': 'raspberry'}
  bramble = Group(*ips, user='pi', connect_kwargs=cxn_args)
  router = bramble[0].run("ip route | grep default | awk '{print $3}'", hide='both').stdout.strip()
  ip_prefix = '.'.join(router.split('.')[:2]) + f".{ip3}"

  print(f"Bramble config. IP prefix: {ip_prefix}")
  for c in bramble:
    print(f"Test connection to {c.host}: ", end='')
    result = c.run('hostname', hide='both')
    print(result.stdout)

  if network:
    print(f"Begin network config. Router IP: {router}")
    config_cluster_network(bramble, router, ip_prefix, reboot_now=True)
    new_ips = [f"{ip_prefix}.{i+1}" for i in range(len(ips))]
    bramble = Group(*new_ips, user='pi', connect_kwargs=cxn_args)

  if init:
    print("Initial raspi-config")
    for c in bramble:
      initial_config(c)

  if nfs:
    print("Setup NFS")
    setup_nfs(bramble, ip_prefix)

  if mpi:
    print("Setup MPI")
    for c in bramble:
      setup_mpi(c)

  if firmware:
    for c in bramble:
      update_firmware(c)

  print("All done, restarting")
  # for c in bramble:
  #   reboot(c)

if __name__ == "__main__":
  parser = argparse.ArgumentParser()
  parser.add_argument("-v", "--verbose", help="Print lots of information (doesn't do anything right now)",
                      action="store_true", default=False)
  parser.add_argument("-n", "--network", action="store_true",)
  parser.add_argument("-i", "--init", action="store_true", help="Initial raspi-config")
  parser.add_argument("-f", "--nfs", action="store_true")
  parser.add_argument("-m", "--mpi", action="store_true")
  parser.add_argument("-a", "--all", action="store_true", dest='configall')
  parser.add_arguement("-s","--firmware", action="store_true")
  args = parser.parse_args()

  if args.configall:
    for k in vars(args):
      setattr(args, k, True)

  main(args.network, args.init, args.nfs, args.mpi)

# When calling 'run', use hide='{out,err,both}' to hide the normal output
# Access with result.stdout, etc.
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
