#!/bin/bash
set -e

# Fill these in with the right values before running (no spaces)
fwtype=${1:-unknownfw}
cooltype=${2:-unknowncool}

HOSTNAME=$(hostname)
TIMESTAMP=$(date +"%Y-%m-%d-%H-%M")
TIME="time"
TIMEFORMAT="%2R"

gettemp() {
    vcgencmd measure_temp | cut -d= -f2 | tr -d "\n'C"
}

thermal_cpu () {
    local maxprime=${1:-25000}
    local iter=${2:-8}
    
    printf -- "----- Thermal Test (CPU) -----\n"

    local i=0
    for ((i=0; i < ${iter}; i++)); do
        gettemp
        printf ","
        time sysbench --test=cpu --cpu-max-prime=$maxprime \
                   --num-threads=4 \run >/dev/null
    done
    printf "Final temp: $(gettemp)\n"
}

thermal_mem_base () {
    local memsize=${1:-3G}

    for ((j=0; j < 10; j++)); do
        sysbench --num-threads=4 --validate=on --test=memory \
                 --memory-block-size=1K --memory-total-size=$memsize \
                 run >/dev/null
    done
}

thermal_mem () {
    local memsize=${1:-3G}
    local iter=${2:-10}

    printf -- "----- Thermal Test (MEM) ----- \n"
    for ((i=0; i < ${iter}; i++)); do
        gettemp
        printf ","
        time thermal_mem_base $memsize
    done
    printf "Final temp: $(gettemp)\n"
}

thermal_cpu 2>&1 | tee thermal-cpu-$(hostname)-${fwtype}-${cooltype}-${TIMESTAMP}.log
sleep 10m # let the pi cooldown
thermal_mem 2>&1 | tee thermal-mem-$(hostname)-${fwtype}-${cooltype}-${TIMESTAMP}.log
