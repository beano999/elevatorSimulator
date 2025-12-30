import os
import threading
import time
from typing import List, Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


class Elevator:
    """Threaded elevator simulation with directional scheduling and duplicate suppression."""

    def __init__(self, num_floors: int):
        if num_floors < 2:
            raise ValueError("Number of floors must be at least 2.")

        self.num_floors = num_floors
        self.current_floor = 1
        self.active_target: Optional[int] = None
        self.direction = "idle"  # idle, up, down
        self.queued_floors: List[int] = []
        self.running = True
        self._condition = threading.Condition()

        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    def _run(self) -> None:
        while self.running:
            with self._condition:
                while self.running and not self.queued_floors:
                    self.direction = "idle"
                    self._condition.wait()
                if not self.running:
                    break

                self.active_target, self.direction = self._pick_next_target()
                self.queued_floors.remove(self.active_target)

            # Move stepwise to allow in-path retargeting.
            while self.running and self.active_target is not None and self.current_floor != self.active_target:
                step = 1 if self.active_target > self.current_floor else -1
                time.sleep(2.0)  # 2s per floor
                with self._condition:
                    retarget = self._retarget_in_path()
                    if retarget is not None and retarget != self.active_target:
                        # Put old target back if it's not already queued.
                        if self.active_target not in self.queued_floors:
                            self.queued_floors.append(self.active_target)
                        self.active_target = retarget
                        if retarget in self.queued_floors:
                            self.queued_floors.remove(retarget)
                        step = 1 if self.active_target > self.current_floor else -1

                    self.current_floor += step

            with self._condition:
                arrived = self.active_target
                self.active_target = None
                if not self.queued_floors:
                    self.direction = "idle"
                self._condition.notify_all()

    def _retarget_in_path(self) -> Optional[int]:
        if self.active_target is None:
            return None
        if self.direction == "up":
            candidates = [f for f in self.queued_floors if self.current_floor < f < self.active_target]
            return min(candidates) if candidates else None
        if self.direction == "down":
            candidates = [f for f in self.queued_floors if self.active_target < f < self.current_floor]
            return max(candidates) if candidates else None
        return None

    def _pick_next_target(self) -> (int, str):
        current = self.current_floor
        dir_state = self.direction
        queue = list(self.queued_floors)

        ups = [f for f in queue if f > current]
        downs = [f for f in queue if f < current]

        if dir_state == "up":
            if ups:
                return min(ups), "up"
            if queue:
                return max(queue), "down"
        if dir_state == "down":
            if downs:
                return max(downs), "down"
            if queue:
                return min(queue), "up"

        target = min(queue, key=lambda f: (abs(f - current), f))
        new_dir = "up" if target > current else "down" if target < current else "idle"
        return target, new_dir

    def queue_floor(self, floor: int) -> str:
        if not (1 <= floor <= self.num_floors):
            raise ValueError(f"Floor must be between 1 and {self.num_floors}.")

        with self._condition:
            if (
                floor == self.current_floor
                or floor == self.active_target
                or floor in self.queued_floors
            ):
                return f"Floor {floor} already requested or current; ignoring duplicate press."

            self.queued_floors.append(floor)
            self._condition.notify_all()
            return f"{floor} queued."

    def snapshot(self) -> Dict:
        with self._condition:
            queued = list(self.queued_floors)
            current = self.current_floor
            active = self.active_target
            direction = self.direction

        floors = []
        for floor in range(1, self.num_floors + 1):
            if floor == current:
                state = "Current"
            elif floor == active:
                state = "Moving"
            elif floor in queued:
                state = "Queued"
            else:
                state = "Available"
            floors.append({"floor": floor, "state": state})

        return {
            "numFloors": self.num_floors,
            "currentFloor": current,
            "activeTarget": active,
            "direction": direction,
            "queue": queued,
            "floors": floors,
        }

    def stop(self) -> None:
        with self._condition:
            self.running = False
            self._condition.notify_all()
        self._worker.join(timeout=1)


class FloorRequest(BaseModel):
    floor: int = Field(..., description="Floor to request")


# Set number of floors from environment variable or default to 10.
DEFAULT_FLOORS = int(os.getenv("ELEVATOR_NUM_FLOORS", "10"))

elevator = Elevator(num_floors=DEFAULT_FLOORS)
app = FastAPI(title="Elevator Simulator")


@app.get("/state")
def get_state():
    return elevator.snapshot()


@app.post("/request")
def request_floor(body: FloorRequest):
    try:
        message = elevator.queue_floor(body.floor)
        return {"status": "ok", "message": message, "state": elevator.snapshot()}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.on_event("shutdown")
def shutdown_event():
    elevator.stop()


STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR, html=True), name="static")


@app.get("/")
def root():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Elevator simulator API. Visit /state or POST to /request."}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("elevator:app", host="127.0.0.1", port=8000, reload=True)