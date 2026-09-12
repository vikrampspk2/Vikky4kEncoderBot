import asyncio

from app.queue.job import Job
from app.queue.manager import JobQueue
from app.queue.dispatcher import Dispatcher


async def main():
    queue = JobQueue()
    dispatcher = Dispatcher(queue)

    job1 = Job(
        job_id="TEST-001",
        user_id=1,
        mode="4K_AI",
        input_path="test.mkv",
    )

    job2 = Job(
        job_id="TEST-002",
        user_id=2,
        mode="4K_HYBRID",
        input_path="test2.mkv",
    )

    await queue.add(job1)
    await queue.add(job2)

    print("QUEUE:", await queue.pending_count())

    await dispatcher.run_once()
    print("QUEUE AFTER JOB-1:", await queue.pending_count())

    await dispatcher.run_once()
    print("QUEUE AFTER JOB-2:", await queue.pending_count())


if __name__ == "__main__":
    asyncio.run(main())
