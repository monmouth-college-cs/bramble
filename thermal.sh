#!/bin/bash
set -e
clear

# Fill these in with the right values before running (no spaces)
fwtype=newfw
cooltype=poe

TIME=/usr/bin/time
TIMECMD="${TIME} -f '%e'"

gettemp() {
    vcgencmd measure_temp | cut -d= -f2 | tr -d "\n'C"
}

thermal_cpu () {
    local maxprime=${1:-25000}
    local iter=${2:-8}
    
    printf -- "----- Thermal Test (CPU) -----\n"
    
    for i in {1..$iter}; do
        gettemp
        printf ","
        ${TIMECMD} sysbench --test=cpu --cpu-max-prime=$maxprime \
                   --num-threads=4 \run >/dev/null
    done
    printf "Final temp: $(gettemp)\n"
}

thermal_mem_base () {
    local memsize=${1:-3G}
    local iter=${2:-10}

    for i in {1..$iter}; do
        sysbench --num-threads=4 --validate=on --test=memory \
                 --memory-block-size=1K --memory-total-size=$memsize \
                 run >/dev/null
    done
}

thermal_mem () {
    local memsize=${1:-3G}
    local iter=${2:-10}

    printf -- "----- Thermal Test (MEM) -----\n"
    for i in {1..$iter}; do
        gettemp
        printf ","
        ${TIMECMD} thermal_mem_base $memsize $iter
    printf "Final temp: $(gettemp)\n"
}

thermal_cpu 500 5 2>&1 | tee thermal-${fwtype}-${cooltype}-cpu.log
sleep 10m # let the pi cooldown
thermal_mem 1M 3 2>&1 | tee thermal-${fwtype}-${cooltype}-mem.log
