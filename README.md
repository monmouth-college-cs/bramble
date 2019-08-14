# Rasperry Pi 4 Bramble

All the scripts and code for our SOfIA 2019 project on cluster computing.

## Running High-Performance Linpack

As of August 6, 2019, I could not get this to work with the mpich
provided by the Raspbian repositories (immediate segfault). It works
if you compile mpich from source, or you can use OpenMPI instead. The
directions below are for OpenMPI.

For maximum performance you should compile Atlas from source. You will
also need to compile HPL, although in both cases you only need to
compile on a single pi.

The directions that follow are slightly modified from a Compute Nodes [blog post](https://computenodes.net/2018/06/28/building-hpl-an-atlas-for-the-raspberry-pi/). They might require changes as software is updated.

### Compiling Atlas

This will take quite a long time. You will have to disable throtting
to compile, so make sure your Pi has a heatsink or (preferably) a fan,
especially for the Pi 4.

I used Atlas version 3.10.3; their might be a newer version for you to use.

```sh
sudo apt install gfortran automake
tar vxjf atlas3.10.3.tar.bz2
mkdir atlas-build # not recommended to build in source dir
cd atlas-build

# disable throttling
echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor

../ATLAS/configure
make # takes a very long time

```

You can re-enable throttling after.

### Compiling HPL

```sh
tar vxzf hpl-2.3.tar.gz
cd hpl-2.3/setup
sh make_generic
cp Make.UNKNOWN ../Make.rpi
cd ..
```

Now you'll need to modify Make.rpi.

```sh
ARCH = rpi
# ...
TOPdir = $(HOME)/src/hpl-2.3
# ...
MPdir = /usr/lib/arm-linux-gnueabihf/openmpi
MPinc = -I $(MPdir)/include
MPlib = $(MPdir)/lib/libmpi.so
# ...
LAdir = /home/pi/src/atlas-build
LAinc =

LAlib = $(LAdir)/lib/libf77blas.a $(LAdir)/lib/libatlas.a
# If you didn't compile Atlas, use next line instead.
LAlib = -lblas
```

### Running HPL

First you'll need to create an MPI host file, which I won't go in to
here. You'll also need an HPL.dat input file. I am not really sure
what the right parameters are, but I used the one provided in the blog
post linked above:

> HPLinpack benchmark input file
> Innovative Computing Laboratory, University of Tennessee
> HPL.out      output file name (if any)
> 6            device out (6=stdout,7=stderr,file)
> 1            # of problems sizes (N)
> 5120         Ns
> 1            # of NBs
> 128          NBs
> 0            PMAP process mapping (0=Row-,1=Column-major)
> 1            # of process grids (P x Q)
> 2            Ps
> 2            Qs
> 16.0         threshold
> 1            # of panel fact
> 2            PFACTs (0=left, 1=Crout, 2=Right)
> 1            # of recursive stopping criterium
> 4            NBMINs (>= 1)
> 1            # of panels in recursion
> 2            NDIVs
> 1            # of recursive panel fact.
> 1            RFACTs (0=left, 1=Crout, 2=Right)
> 1            # of broadcast
> 1            BCASTs (0=1rg,1=1rM,2=2rg,3=2rM,4=Lng,5=LnM)
> 1            # of lookahead depth
> 1            DEPTHs (>=0)
> 2            SWAP (0=bin-exch,1=long,2=mix)
> 64           swapping threshold
> 0            L1 in (0=transposed,1=no-transposed) form
> 0            U  in (0=transposed,1=no-transposed) form
> 1            Equilibration (0=no,1=yes)
> 8            memory alignment in double (> 0)

Tuning details can be found [here](http://www.netlib.org/benchmark/hpl/tuning.html).

### Tuning

Problem Sizes: 8 nodes with 2 GB memory each = 16 GB = 2^4 x 2^30 = 2^34 bytes
double precision = 8 bytes = 2^3
So we can hold 2^34 / 2^3 = 2^31 \approx 2 billion elements in memory
Use only 80% (save for OS): about 1.7 million
Square root of this to get problem size (matrices): (sqrt (* 0.8 (expt 2 31)))41448.60574735898
But it seems the process gets killed with 40960...

Block size: try out some in 32..256 range: 32 64 128 256

Grids: Normally use a 1:k ration with k in [1..3], with Q slightly larger. However, with a simple Ethernet network, "there is only one wire through which all the messages are exchanged" (from HPL FAQ, but is it true?), so flat grids are preferred: 1 x 4, 1 x 8, 2 x 4, etc.
Try out: 4x8, 2x16
