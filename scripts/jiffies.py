#!/usr/bin/env python3

import argparse
import time
import sys
import statistics

# Note: Bash equivalent (consider fork() overhead)
# time bash -c "for i in {1..100}; do sleep 0.010; done"

def sleep_loop(ms, n):
    t_sleeping = n * ms
    t_stamps = []
    print(f'Requested sleep of {ms} ms * {n} time(s) = {t_sleeping} ms')
    t_stamps.append(time.time())
    for i in range(0,n):
        time.sleep(ms/1000.0)
        t_stamps.append(time.time())

    t_duration = (t_stamps[-1] - t_stamps[0]) * 1000
    print(f'The process took {t_duration} ms')
    print(f'Drift: {t_duration} / {t_sleeping} = {(t_duration / t_sleeping * 100)-100} %')

    t_splits = [(t_stamps[i] - t_stamps[i-1])*1000 for i in range(1,len(t_stamps))]
    print(f'Average sleep cycle: {statistics.mean(t_splits)} ms')
    print(f'Median sleep cycle:  {statistics.median(t_splits)} ms')
    print(f'Max sleep cycle:     {max(t_splits)} ms')
    print(f'Min sleep cycle:     {min(t_splits)} ms')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Check your jiffies')
    parser.add_argument('--duration', type=int, default=10, help='Sleep duration cycle in ms')
    parser.add_argument('--cycles', type=int, default=1000, help='Number of sleep cycles')
    args = parser.parse_args()
    sleep_loop(args.duration, args.cycles)
