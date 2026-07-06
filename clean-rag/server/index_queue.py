"""Sequential indexing queue for acquire-topic auto-index operations.

When multiple parallel research agents call POST /acquire-topic at the same
time (common when working on a new topic area), their auto-index steps land
here and process one at a time. This prevents concurrent embedding operations
from stacking RAM usage and overloading the machine.

Only acquire-topic uses this queue. Direct POST /index-topic, POST /batch-index,
and POST /index-project are not affected.

Design grounded in:
- Python asyncio.Queue with single worker (docs.python.org/3/library/asyncio-queue)
- ChromaDB must run via run_in_executor, not in asyncio coroutines
  (docs/RAG-ARCHITECTURE.md:412-426)
- GC and ChromaStore.evict_cache already fire inside index_topic()
  (clean-rag/server/indexing.py:623-625)
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from functools import partial
from typing import Any

from .indexing import index_topic

logger = logging.getLogger(__name__)


@dataclass
class IndexJob:
    """A queued indexing job."""
    topic: str
    category: str | None
    force: bool
    submitted_at: float = field(default_factory=time.time)
    result: dict | None = None
    error: str | None = None


class IndexQueue:
    """Processes acquire-topic index jobs one at a time.

    Usage:
        queue = IndexQueue()
        queue.start(embedder)       # call once at app startup
        job = queue.submit("react", category="frontend")
        # job is processed in the background, one at a time
        queue.stop()                # call on shutdown
    """

    def __init__(self, maxsize: int = 50):
        self._queue: asyncio.Queue[IndexJob] = asyncio.Queue(maxsize=maxsize)
        self._worker_task: asyncio.Task | None = None
        self._embedder = None
        self._active_job: IndexJob | None = None
        self._completed: list[dict] = []
        self._max_completed = 20

    def start(self, embedder) -> None:
        """Start the background worker. Call once after app init."""
        self._embedder = embedder
        self._worker_task = asyncio.create_task(self._worker())
        logger.info("Index queue worker started (maxsize=%d)", self._queue.maxsize)

    async def stop(self) -> None:
        """Stop the worker gracefully."""
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        logger.info("Index queue worker stopped")

    def submit(self, topic: str, category: str | None = None, force: bool = True) -> dict:
        """Submit a topic for background indexing. Returns immediately.

        Returns a dict with queue position info. Does not block.
        Deduplicates: if the same topic is already pending, skips it.
        """
        # Check for duplicates in the queue
        pending = list(self._queue._queue)
        for job in pending:
            if job.topic == topic:
                logger.info("Topic '%s' already queued, skipping duplicate", topic)
                return {
                    "index": "already_queued",
                    "topic": topic,
                    "queue_position": self._pending_position(topic),
                }

        # Also skip if this topic is currently being indexed
        if self._active_job and self._active_job.topic == topic:
            return {
                "index": "in_progress",
                "topic": topic,
            }

        job = IndexJob(topic=topic, category=category, force=force)

        try:
            self._queue.put_nowait(job)
        except asyncio.QueueFull:
            logger.warning("Index queue is full (maxsize=%d), dropping topic '%s'",
                           self._queue.maxsize, topic)
            return {
                "index": "queue_full",
                "topic": topic,
                "queue_size": self._queue.qsize(),
            }

        position = self._queue.qsize()
        logger.info("Queued topic '%s' for indexing (position %d)", topic, position)
        return {
            "index": "queued",
            "topic": topic,
            "queue_position": position,
        }

    def status(self) -> dict:
        """Return current queue state for GET /queue."""
        pending = []
        for job in list(self._queue._queue):
            pending.append({
                "topic": job.topic,
                "category": job.category,
                "submitted_at": job.submitted_at,
            })

        active = None
        if self._active_job:
            active = {
                "topic": self._active_job.topic,
                "category": self._active_job.category,
                "started_at": self._active_job.submitted_at,
            }

        return {
            "active": active,
            "pending": pending,
            "pending_count": len(pending),
            "completed_recent": self._completed[-self._max_completed:],
            "worker_running": self._worker_task is not None and not self._worker_task.done(),
        }

    def _pending_position(self, topic: str) -> int:
        """Find the position of a topic in the pending queue."""
        for i, job in enumerate(list(self._queue._queue)):
            if job.topic == topic:
                return i + 1
        return -1

    async def _worker(self) -> None:
        """Background worker: pull one job at a time, index it."""
        logger.info("Index queue worker running")
        loop = asyncio.get_running_loop()

        while True:
            try:
                job = await self._queue.get()
            except asyncio.CancelledError:
                logger.info("Index queue worker cancelled")
                return

            self._active_job = job
            start = time.time()
            logger.info("Processing queued index: topic='%s' (category=%s)",
                        job.topic, job.category)

            try:
                # Warm up embedder if needed (blocking, use executor)
                if self._embedder and not self._embedder.is_loaded:
                    await loop.run_in_executor(None, self._embedder.embed_query, "warmup")

                if self._embedder and self._embedder.is_loaded:
                    result = await loop.run_in_executor(
                        None,
                        partial(index_topic, job.topic, self._embedder,
                                force=job.force, category=job.category),
                    )
                    job.result = result
                    elapsed = round(time.time() - start, 1)
                    logger.info("Queued index done: topic='%s' chunks=%d elapsed=%.1fs",
                                job.topic, result.get("chunks_created", 0), elapsed)
                else:
                    job.error = "Embedder not available"
                    logger.warning("Skipping queued index for '%s': embedder not loaded",
                                   job.topic)

            except Exception as e:
                job.error = str(e)
                logger.error("Queued index failed for '%s': %s", job.topic, e)

            # Record completion
            self._completed.append({
                "topic": job.topic,
                "category": job.category,
                "elapsed_s": round(time.time() - start, 1),
                "chunks_created": job.result.get("chunks_created", 0) if job.result else 0,
                "error": job.error,
                "completed_at": time.time(),
            })

            # Trim completed list
            if len(self._completed) > self._max_completed:
                self._completed = self._completed[-self._max_completed:]

            self._active_job = None
            self._queue.task_done()
