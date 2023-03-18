import asyncio
import json
import logging
import random
from typing import List

from fastapi import FastAPI, WebSocket

app = FastAPI()
logging.basicConfig(level=logging.INFO,
                    format="%(levelname)s:  %(asctime)s  %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S")


class Node:
    def __init__(self, id, neighbors_in, neighbors_out):
        self.id = id
        self.load = random.randint(0, 100)
        self.neighbors_in = neighbors_in
        self.neighbors_out = neighbors_out
        self.received = {neighbor: False for neighbor in neighbors_in}
        self.initiator = False
        self.inc = {id}
        self.ninc = set()

    async def send_to_neighbors(self, struct, websocket: WebSocket):
        if self.try_terminate(struct):
            return
        old_inc = self.copy_inc(struct)
        old_ninc = self.copy_ninc(struct)
        for neighbor in self.neighbors_out:
            await struct[neighbor].receive(self, struct, websocket)
        if self.try_terminate(struct):
            return
        new_inc = self.copy_inc(struct)
        new_ninc = self.copy_ninc(struct)
        for id in self.neighbors_out:
            if old_inc[id] != new_inc[id] or old_ninc[id] != new_ninc[id]:
                await struct[id].send_to_neighbors(struct, websocket)

    def copy_inc(self, struct):
        old_inc = {}
        for neighbor in self.neighbors_out:
            old_inc[neighbor] = struct[neighbor].inc
        return old_inc

    def copy_ninc(self, struct):
        old_ninc = {}
        for neighbor in self.neighbors_out:
            old_ninc[neighbor] = struct[neighbor].ninc
        return old_ninc

    async def receive(self, sender, struct, websocket: WebSocket):
        if self.try_terminate(struct):
            return
        self.inc = self.inc | sender.inc
        self.ninc = self.ninc | sender.ninc
        self.received[sender.id] = True
        if all(rec is True for rec in self.received.values()):
            self.ninc = self.ninc | {self.id}
        await websocket.send_text(str(self))
        await asyncio.sleep(1)

    def try_terminate(self, struct):
        return self.get_initiator(struct).inc == self.get_initiator(struct).ninc

    def get_initiator(self, struct):
        return [value for key, value in struct.items() if value.initiator is True][0]

    def __str__(self):
        return f"Вычислительный узел №{self.id}: Нагрузка {self.load}%"

    @staticmethod
    async def init(struct, id, websocket: WebSocket):
        struct[id].initiator = True
        await struct[id].send_to_neighbors(struct, websocket)


def make_topology_in(topology_out: dict[int, List[int]]):
    result = {}
    for node, edges in topology_out.items():
        for edge in edges:
            if edge not in result:
                result[edge] = []
            result[edge].append(node)

    return dict(sorted(result.items()))  # type: ignore


@app.websocket("/")
async def root(websocket: WebSocket):
    await websocket.accept()
    json_data = await websocket.receive_text()
    initiator = int(await websocket.receive_text())

    # Parse JSON data into dictionary
    res = json.loads(json.loads(json_data))['items']
    topology_out = {item['id']: [int(x.strip()) for x in item['items']] for item in res}
    topology_in = make_topology_in(topology_out)
    struct = {}
    for id in topology_out.keys():
        struct[id] = Node(id, topology_in[id], topology_out[id])

    await Node.init(struct, initiator, websocket)
