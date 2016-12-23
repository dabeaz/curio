# Write the benchmarking functions here.
# See "Writing benchmarks" in the asv docs for more information.

import curio

async def reschedule_loop(count):
    for _ in range(count):
        await curio.sleep(0)


def time_scheduler_1_task_200_000_reschedules():
    curio.run(reschedule_loop(200000))


def time_scheduler_100_tasks_2_000_reschedules():
    async def main():
        for _ in range(100):
            await curio.spawn(reschedule_loop(2000))
    curio.run(main())
