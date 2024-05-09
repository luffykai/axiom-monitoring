import argparse
import json
import time

from web3 import Web3


SYNC_THRESHOLD = 224

class AxiomMonitoring:
    def __init__(self):
        # sorted, disjoint ranges
        self.cached_ranges: list[list[int]] = []

    def merge_ranges(self):
        merged = []
        for r in sorted(self.cached_ranges, key=lambda t: t[0]):
            if len(merged) == 0 or merged[-1][1] < r[0]:  # no overlap
                merged.append(r)
            else:
                merged[-1][1] = max(merged[-1][1], r[1])

        self.cached_ranges = merged

    def add_range(self, r: list[int]):
        self.cached_ranges.append(r)
        self.merge_ranges()
    
    def process_events(self, events):
        for event in events:
            self.add_range(
                r=[
                    event.args.startBlockNumber,
                    event.args.startBlockNumber + event.args.numFinal,
                ]
            ) 


def process_history(
    contract,
    m: AxiomMonitoring,
    current_block_number: int,
    skip_from: int | None,
    skip_val: int | None,
):
    if skip_from and skip_val:
        # i've run this before, no need to rerun every time
        start_block = skip_from
        m.cached_ranges = [[0, skip_val]]
    else:
        m.cached_ranges = []
        # get all the historic events
        events = contract.events.HistoricalRootUpdated.create_filter(
            fromBlock=0, toBlock=19000000
        ).get_all_entries()
        m.process_events(events)
        start_block = 19000000

    step = 1000
    for left in range(start_block, current_block_number, step):

        # TODO: handle when events too many?
        events = contract.events.HistoricalRootUpdated.create_filter(
            fromBlock=left, toBlock=left + step
        ).get_all_entries()
        m.process_events(events)


def main(api_key: str, address: str, interval: int):
    url = f"https://mainnet.infura.io/v3/{api_key}"
    web3 = Web3(Web3.HTTPProvider(url))
    current_block_number = web3.eth.block_number

    with open("abi.json", "r") as f:
        abi = json.loads(f.read())["result"]
    contract = web3.eth.contract(address=address, abi=abi)

    m = AxiomMonitoring()
    process_history(
        contract,
        m,
        current_block_number=current_block_number,
        skip_from=19813000,
        skip_val=19813548,
    )
    assert(m.cached_ranges[0][0] == 0)

    event_filter = contract.events.HistoricalRootUpdated.create_filter(
        fromBlock=current_block_number,
    )

    previous_sync = True
    while True:
        try:
            events = event_filter.get_new_entries()
            m.process_events(events)
    
            latest = web3.eth.block_number
            oldest_not_cached = m.cached_ranges[0][1]
            in_sync = oldest_not_cached > latest - SYNC_THRESHOLD
            status = "sync" if in_sync else "out of sync"
            if not in_sync and previous_sync:
                # TODO: integrate with alert system to fire the alert
                # Here we just print out the status
                print("Alert: not in sync!!")
            elif in_sync and not previous_sync:
                # TODO: resolve previous out-of-sync alert if any
                # Here we just print out the status
                print("Alert: now in sync!!")
            print(f"Status: {status}: latest block: {latest}, oldest not cached: {oldest_not_cached}")
    
            previous_sync = in_sync
        except Exception as e:
            print(f"Error happened, will continue: {e}")
        time.sleep(interval)

if __name__ == "__main__": 
    parser = argparse.ArgumentParser()
    parser.add_argument("api_key", type=str, help="the infura api key")
    parser.add_argument("--address", type=str, help="contract address of AxiomV2Core",
                        default="0x69963768F8407dE501029680dE46945F838Fc98B")
    parser.add_argument("--interval", type=int, default=10, help="poll interval in seconds")
    args = parser.parse_args()
    main(args.api_key, args.address, args.interval)
