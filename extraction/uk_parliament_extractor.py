"""
UK Parliament Bills API + Commons Votes API extractor.

Fetches bill lifecycle stages and division (vote) data, yielding normalized
events compatible with the DAO event schema for process mining comparison.

Data sources:
  - Bills API: https://bills-api.parliament.uk/api/v1/
  - Commons Votes API: https://commonsvotes-api.parliament.uk/data/
"""

import json
import time
import requests
from typing import Iterator, Dict, Any, Optional
from datetime import datetime

BILLS_API = "https://bills-api.parliament.uk/api/v1"
VOTES_API = "https://commonsvotes-api.parliament.uk/data"

PAGE_SIZE = 20
REQUEST_DELAY = 0.3

STAGE_ORDER = {
    6: "1st Reading (Commons)",
    7: "2nd Reading (Commons)",
    8: "Committee Stage (Commons)",
    9: "Report Stage (Commons)",
    10: "3rd Reading (Commons)",
    1: "1st Reading (Lords)",
    2: "2nd Reading (Lords)",
    3: "Committee Stage (Lords)",
    4: "Report Stage (Lords)",
    5: "3rd Reading (Lords)",
    11: "Royal Assent",
    12: "Consideration of Lords Amendments",
    13: "Consideration of Commons Amendments",
    14: "Programme Motion",
    15: "Money Resolution",
    16: "Lords Examiners",
    17: "Commons Examiners",
    18: "Carry-over Motion",
    25: "2nd Reading Committee (Commons)",
    30: "2nd Reading Committee (Lords)",
    36: "Ways and Means Resolution",
    38: "Legislative Grand Committee",
    39: "Reconsideration",
    40: "Consequential Consideration",
    42: "Consideration of Lords Message",
    43: "Select Committee Stage",
    49: "Committee of the Whole House",
}


def _get(url: str, params: dict = None) -> Optional[dict]:
    """Rate-limited GET with retry."""
    for attempt in range(3):
        try:
            time.sleep(REQUEST_DELAY)
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as e:
            if resp.status_code == 429:
                wait = 2 ** (attempt + 1)
                print(f"  Rate limited, waiting {wait}s...")
                time.sleep(wait)
                continue
            if resp.status_code == 404:
                return None
            raise
        except requests.exceptions.RequestException:
            if attempt < 2:
                time.sleep(2)
                continue
            raise
    return None


def fetch_all_bills(session_id: Optional[int] = None,
                    is_act: Optional[bool] = None) -> Iterator[Dict[str, Any]]:
    """Paginate through all bills from the Bills API."""
    skip = 0
    total = None

    while True:
        params = {
            "Skip": skip,
            "Take": PAGE_SIZE,
            "SortOrder": "DateUpdatedAscending",
        }
        if session_id is not None:
            params["Session"] = session_id
        if is_act is not None:
            params["IsDefeated"] = not is_act  # approximate filter

        data = _get(f"{BILLS_API}/Bills", params)
        if not data or not data.get("items"):
            break

        if total is None:
            total = data.get("totalResults", 0)
            print(f"  Total bills to fetch: {total}")

        for bill in data["items"]:
            yield bill

        skip += PAGE_SIZE
        if skip >= total:
            break


def fetch_bill_detail(bill_id: int) -> Optional[Dict[str, Any]]:
    """Fetch full bill detail including sponsors and summary."""
    return _get(f"{BILLS_API}/Bills/{bill_id}")


def fetch_bill_stages(bill_id: int) -> list:
    """Fetch all stages for a bill."""
    data = _get(f"{BILLS_API}/Bills/{bill_id}/Stages", {"Take": 100})
    if not data:
        return []
    return data.get("items", [])


def fetch_divisions_for_bill(bill_title: str) -> list:
    """
    Search Commons Votes API for divisions mentioning the bill title.
    The API doesn't support billId linking, so we match by title substring.
    """
    search_term = bill_title.replace(" Bill", "").strip()
    data = _get(f"{VOTES_API}/divisions.json/search",
                {"queryParameters.searchTerm": search_term, "take": 100})
    if not data:
        return []
    return data if isinstance(data, list) else data.get("items", data)


def fetch_division_detail(division_id: int) -> Optional[Dict[str, Any]]:
    """Fetch full division detail with individual MP votes."""
    return _get(f"{VOTES_API}/division/{division_id}.json")


def extract_bill_events(bill_summary: dict,
                        include_votes: bool = True) -> Iterator[Dict[str, Any]]:
    """
    Extract all events for a single bill: stage transitions + division votes.
    Yields dicts matching the DAO event schema.
    """
    bill_id = bill_summary["billId"]
    short_title = bill_summary.get("shortTitle", f"Bill {bill_id}")
    case_id = f"bill_{bill_id}"

    detail = fetch_bill_detail(bill_id)
    sponsor_name = None
    if detail and detail.get("sponsors"):
        first = detail["sponsors"][0]
        if first.get("member"):
            sponsor_name = first["member"].get("name")
        elif first.get("organisation"):
            sponsor_name = first["organisation"].get("name")

    bill_meta = {
        "bill_type_id": bill_summary.get("billTypeId"),
        "originating_house": bill_summary.get("originatingHouse"),
        "is_act": bill_summary.get("isAct"),
        "is_defeated": bill_summary.get("isDefeated"),
    }

    # Stage events
    stages = fetch_bill_stages(bill_id)
    for stage in stages:
        stage_id = stage.get("stageId")
        description = stage.get("description", STAGE_ORDER.get(stage_id, f"Stage {stage_id}"))
        house = stage.get("house", "")

        sittings = stage.get("stageSittings", [])
        if sittings:
            for sitting in sittings:
                ts = sitting.get("date")
                if ts:
                    yield {
                        "id": f"ukp_stage_{bill_id}_{stage.get('id')}_{sitting.get('id')}",
                        "source": "uk_parliament_bills",
                        "event_type": description,
                        "timestamp": ts,
                        "proposal_id": case_id,
                        "proposal_title": short_title,
                        "proposal_author": sponsor_name,
                        "proposal_state": bill_summary.get("currentHouse"),
                        "voter": None,
                        "voting_power": None,
                        "choice": None,
                        "tx_hash": None,
                        "block_number": None,
                        "log_index": None,
                        "contract_address": None,
                        "raw_data": json.dumps({
                            "stage_id": stage_id,
                            "bill_stage_id": stage.get("id"),
                            "sitting_id": sitting.get("id"),
                            "house": house,
                            "abbreviation": stage.get("abbreviation"),
                            "sort_order": stage.get("sortOrder"),
                            **bill_meta,
                        }),
                    }
        else:
            yield {
                "id": f"ukp_stage_{bill_id}_{stage.get('id')}_nosit",
                "source": "uk_parliament_bills",
                "event_type": description,
                "timestamp": bill_summary.get("lastUpdate"),
                "proposal_id": case_id,
                "proposal_title": short_title,
                "proposal_author": sponsor_name,
                "proposal_state": bill_summary.get("currentHouse"),
                "voter": None,
                "voting_power": None,
                "choice": None,
                "tx_hash": None,
                "block_number": None,
                "log_index": None,
                "contract_address": None,
                "raw_data": json.dumps({
                    "stage_id": stage_id,
                    "bill_stage_id": stage.get("id"),
                    "house": house,
                    "abbreviation": stage.get("abbreviation"),
                    "sort_order": stage.get("sortOrder"),
                    "no_sitting_date": True,
                    **bill_meta,
                }),
            }

    if not include_votes:
        return

    # Division events — same case as the bill for end-to-end traces
    divisions = fetch_divisions_for_bill(short_title)
    for div in divisions:
        div_id = div.get("DivisionId")
        div_date = div.get("Date")
        div_title = div.get("Title", "")

        yield {
            "id": f"ukp_division_{div_id}",
            "source": "uk_parliament_votes",
            "event_type": "Division",
            "timestamp": div_date,
            "proposal_id": case_id,
            "proposal_title": short_title,
            "proposal_author": sponsor_name,
            "proposal_state": None,
            "voter": None,
            "voting_power": None,
            "choice": json.dumps({
                "ayes": div.get("AyeCount"),
                "noes": div.get("NoCount"),
            }),
            "tx_hash": None,
            "block_number": None,
            "log_index": None,
            "contract_address": None,
            "raw_data": json.dumps({
                "division_id": div_id,
                "division_title": div_title,
                "division_number": div.get("Number"),
                "aye_count": div.get("AyeCount"),
                "no_count": div.get("NoCount"),
                **bill_meta,
            }),
        }

        div_detail = fetch_division_detail(div_id)
        if not div_detail:
            continue

        for voter in (div_detail.get("Ayes") or []):
            yield _mp_vote_event(voter, div_id, div_date, "Aye",
                                 case_id, short_title, sponsor_name, bill_meta)
        for voter in (div_detail.get("Noes") or []):
            yield _mp_vote_event(voter, div_id, div_date, "No",
                                 case_id, short_title, sponsor_name, bill_meta)


def _mp_vote_event(mp: dict, div_id: int, timestamp: str, choice: str,
                   case_id: str, title: str, author: str,
                   bill_meta: dict) -> Dict[str, Any]:
    member_id = mp.get("MemberId")
    return {
        "id": f"ukp_vote_{div_id}_{member_id}",
        "source": "uk_parliament_votes",
        "event_type": "Vote",
        "timestamp": timestamp,
        "proposal_id": case_id,
        "proposal_title": title,
        "proposal_author": author,
        "proposal_state": None,
        "voter": mp.get("Name"),
        "voting_power": 1.0,
        "choice": json.dumps({
            "vote": choice,
            "party": mp.get("Party"),
            "constituency": mp.get("MemberFrom"),
        }),
        "tx_hash": None,
        "block_number": None,
        "log_index": None,
        "contract_address": None,
        "raw_data": json.dumps({
            "member_id": member_id,
            "party": mp.get("Party"),
            "party_abbreviation": mp.get("PartyAbbreviation"),
            "constituency": mp.get("MemberFrom"),
            "division_id": div_id,
            "proxy_name": mp.get("ProxyName"),
            **bill_meta,
        }),
    }


def extract_all(session_id: Optional[int] = None,
                include_votes: bool = True) -> Iterator[Dict[str, Any]]:
    """
    Extract all bill lifecycle + vote events.
    Yields normalized event dicts.
    """
    print(f"Fetching bills from UK Parliament Bills API...")
    bill_count = 0

    for bill in fetch_all_bills(session_id=session_id):
        bill_count += 1
        title = bill.get("shortTitle", f"Bill {bill['billId']}")
        print(f"  [{bill_count}] {title} (id={bill['billId']})")

        yield from extract_bill_events(bill, include_votes=include_votes)

    print(f"Completed: processed {bill_count} bills")
