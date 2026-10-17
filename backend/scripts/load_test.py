"""Load test: starts the API, fires N concurrent ticket submissions through the full
pipeline (classify -> retrieve -> draft -> route), then drains the outbox and reports
end-to-end throughput. Honest numbers land in the README."""
import argparse
import asyncio
import os
import signal
import statistics
import subprocess
import sys
import tempfile
import time

import httpx
import pgserver

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def post_ticket(client, i, results):
    t0 = time.perf_counter()
    r = await client.post("/tickets", json={
        "subject": f"Load ticket {i}: how do I export data? variant {i}",
        "body": f"How do I export workspace data as JSON? Context {i}: we need "
                f"everything for our audit. Ref #{i}",
        "customer_email": f"load{i}@loadgen.example",
        "external_id": f"load-{i}",
    }, headers={"X-API-Token": "dev-token"})
    results.append((time.perf_counter() - t0, r.status_code))


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("-n", type=int, default=500)
    parser.add_argument("--concurrency", type=int, default=25)
    parser.add_argument("--ci", action="store_true",
                        help="accepted for CI readability; behavior is env-driven")
    args = parser.parse_args()

    if not os.environ.get("DATABASE_URL"):
        os.environ["DATABASE_URL"] = pgserver.get_server(
            tempfile.mkdtemp(prefix="resolvedesk-load-pg")).get_uri().replace(
                "postgresql://", "postgresql+psycopg2://")
    env = dict(os.environ)
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", "8123",
         "--log-level", "warning"],
        env=env, cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        for _ in range(60):
            try:
                httpx.get("http://127.0.0.1:8123/health", timeout=1)
                break
            except httpx.HTTPError:
                time.sleep(0.5)
        else:
            print("server failed to start")
            return 1

        results: list[tuple[float, int]] = []
        sem = asyncio.Semaphore(args.concurrency)

        async def bounded(client, i):
            async with sem:
                await post_ticket(client, i, results)

        t0 = time.perf_counter()
        async with httpx.AsyncClient(base_url="http://127.0.0.1:8123", timeout=60) as c:
            await asyncio.gather(*(bounded(c, i) for i in range(args.n)))
        ingest_s = time.perf_counter() - t0

        lat = sorted(x[0] for x in results)
        codes = {}
        for _, code in results:
            codes[code] = codes.get(code, 0) + 1

        # drain the outbox with the real worker
        from app import db
        from app.outbox import run_once

        db.init()
        t1 = time.perf_counter()
        while True:
            out = run_once(db.session, batch_size=50)
            if out["done"] == 0 and out["retry"] == 0 and out["failed"] == 0:
                break
        drain_s = time.perf_counter() - t1

        p50 = statistics.median(lat)
        p95 = lat[int(0.95 * len(lat)) - 1]
        print(f"tickets={args.n} concurrency={args.concurrency}")
        print(f"ingest+pipeline: {ingest_s:.1f}s total, {args.n/ingest_s:.0f} tickets/s, "
              f"p50={p50*1000:.0f}ms p95={p95*1000:.0f}ms")
        print(f"status codes: {codes}")
        print(f"outbox drain: {drain_s:.1f}s ({args.n/drain_s:.0f} side effects/s)")
        print(f"end-to-end: {ingest_s + drain_s:.1f}s")
        failed = sum(v for k, v in codes.items() if k != 201)
        return 0 if failed == 0 else 1
    finally:
        server.send_signal(signal.SIGTERM)
        server.wait(timeout=10)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
