#!/bin/bash
set -e
if [ "$UID" != "0" ]; then
    echo "This script must be run with sudo."
    exit
fi

## @TODO: optional argument to add /boot/hostname file with a hostname

##### Parameter Variables #####
mount_boot=/mnt/rpiboot
mount_root=/mnt/rpiroot
imgname=bramble.img
firmware=data/vl805_update_0137a8.zip
keyfile=authorized_keys

##### Image Downloading #####
if [ ! -f $imgname ]; then
    echo "Downloading latest raspbian image"
    wget https://downloads.raspberrypi.org/raspbian_lite_latest -O base.zip
    echo "Image downloaded, unzipping now"
    unzip base.zip
    mv *.img base.img
    echo "Copying"
    cp base.img $imgname
fi


##### Mounting #####

# Need to be "superuser" for this stuff
mkdir -p $mount_boot $mount_root
sector_size=512 # Use `fdisk -l $imgname` to verify that 512 is correct

disk_info="$(fdisk --bytes -lo Id,Start,Size $imgname)"

#### Mount boot partition ####
partition_info="$(grep '^ c' <<< \"$disk_info\")"

partition_start=$(echo "$partition_info" | awk '{print $2}')
partition_size=$(echo "$partition_info" | awk '{print $3}')
offset=$(($sector_size * $partition_start))
echo "[Mount boot] Calculated offset of $offset, size of $partition_size, mounting boot image at $mount_boot"
mount -o loop,offset=$offset,sizelimit=$partition_size $imgname $mount_boot

partition_info="$(grep '^83' <<< \"$disk_info\")"
partition_start=$(echo $partition_info | awk '{print $2}')
partition_size=$(echo $partition_info | awk '{print $3}')
offset=$(($sector_size * $partition_start))
echo "[Mount root] Calculated offset of $offset, size of $partition_size, mounting root image at $mount_root"
mount -o loop,offset=$offset,sizelimit=$partition_size $imgname $mount_root

##### Enabling SSH #####
echo "Enabling ssh"
touch ${mount_boot}/ssh

# @TODO: Just use fabric for this
##### Copying Firmware #####
# echo "Copying updated firmware"
# mkdir -p ${mount_root}/home/pi/firmware
# cp $firmware ${mount_root}/home/pi/firmware/firmware_update.zip

# @TODO: use ssh-copy-id, take in keyfile argument
##### Copying SSH Keys #####
# if [ -f "./authorized_keys" ]; then
#     echo "Found local authorized_keys, copying to image."
#     mkdir -p ${mount_root}/.ssh
#     cat $keyfile >> ${mount_root}/.ssh/authorized_keys
# else
#     echo "No SSH keys found."
# fi

##### Unmounting #####
echo "Unmounting $mount_boot $mount_root"
umount $mount_boot $mount_root
rm -rf $mount_boot $mount_root
echo "All done! Use 'dd bs=4M if=bramble.img of=/dev/<SDCARD>' to transfer to an SD card. Replace '<SDCARD>' with the device name."
