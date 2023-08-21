"""
Shows how you can achieve functionality like ClickHouse's AggregatingMergeTree engine.
This example keeps track of a running count of events per user.

Counting is just a sum of occurrences, so we simply can create a custom merge query that introduces a new
column called `cnt` when merged. We then add that column during ingestion with a default of `1`.
Then we sum that to get the count of rows, constantly reducing the number of rows when merged.

It's important that we apply the same sum to query the data as
merging does not guarantee reducing to a single row, as data across parts may not fully merge.
For end-user querying you could always replace a fake table state-finisher with this as a subquery.

Run:
`docker compose up -d`

Then:
`python custom-merge-aggregation.py`
"""

from icedb.icedb import IceDBv3, CompressionCodec
from icedb.log import IceLogIO
from datetime import datetime
import json
from time import time
from helpers import get_local_ddb, get_local_s3_client, delete_all_s3, get_ice

s3c = get_local_s3_client()


def part_func(row: dict) -> str:
    """
    We'll partition by user_id, date
    """
    row_time = datetime.utcfromtimestamp(row['ts'] / 1000)
    part = f"u={row['user_id']}/d={row_time.strftime('%Y-%m-%d')}"
    return part


def format_row(row: dict) -> dict:
    """
    Considering this would be a materialized view on raw incoming data,
    we prepare it differently than `simple-full.py`
    """
    del row['properties'] # drop properties because we don't need it for this table
    return row


ice = get_ice(s3c, part_func, format_row)

# Some fake events that we are ingesting, pretending we are inserting a second time into a materialized view
example_events = [
    {
        "ts": 1686176939445,
        "event": "page_load",
        "user_id": "user_a",
        "properties": {
            "page_name": "Home"
        },
    }, {
        "ts": 1676126229999,
        "event": "page_load",
        "user_id": "user_b",
        "properties": {
            "page_name": "Home"
        },
    }, {
        "ts": 1686176939666,
        "event": "page_load",
        "user_id": "user_a",
        "properties": {
            "page_name": "Settings"
        },
    }, {
        "ts": 1686176941445,
        "event": "page_load",
        "user_id": "user_a",
        "properties": {
            "page_name": "Home"
        },
    }
]

print("============= inserting events ==================")
inserted = ice.insert(example_events)
firstInserted = list(map(lambda x: x.path, inserted))
print('inserted', firstInserted)

# Read the state in
log = IceLogIO("dan-mbp")
s1, f1, t1, l1 = log.read_at_max_time(s3c, round(time() * 1000))
alive_files = list(filter(lambda x: x.tombstone is None, f1))

print("============= check number of raw rows in data =============")
# Create a duckdb instance for querying
ddb = get_local_ddb()

# Run the query
s1, f1, t1, l1 = log.read_at_max_time(s3c, round(time() * 1000))
alive_files = list(filter(lambda x: x.tombstone is None, f1))
query = ("select user_id, count(*) as cnt "
         "from read_parquet([{}]) "
         "group by user_id, event "
         "order by count(user_id) desc").format(
    ', '.join(list(map(lambda x: "'s3://" + ice.s3c.s3bucket + "/" + x.path + "'", alive_files)))
)
print(ddb.sql(query))

print("============= perform query that shows the running count =============")

# Run the query
s1, f1, t1, l1 = log.read_at_max_time(s3c, round(time() * 1000))
alive_files = list(filter(lambda x: x.tombstone is None, f1))
query = ("""
select user_id, event, sum(ifnull(cnt, 1)) as cnt
from (
    select * from values (null, null, null) f(user_id, event, cnt)
    union all by name
    select user_id, event, cnt
    from read_parquet([{}])
)
where event is not null
group by user_id, event
order by sum(cnt) desc
""").format(
    ', '.join(list(map(lambda x: "'s3://" + ice.s3c.s3bucket + "/" + x.path + "'", alive_files)))
)
print(ddb.sql(query))

print("============= inserting more events ==================")
inserted = ice.insert(example_events)
firstInserted = list(map(lambda x: x.path, inserted))
print('inserted (again)', firstInserted)

print("============= check number of raw rows in data =============")

# Run the query
s1, f1, t1, l1 = log.read_at_max_time(s3c, round(time() * 1000))
alive_files = list(filter(lambda x: x.tombstone is None, f1))
query = ("select user_id, count(*) as cnt "
         "from read_parquet([{}]) "
         "group by user_id, event "
         "order by count(user_id) desc").format(
    ', '.join(list(map(lambda x: "'s3://" + ice.s3c.s3bucket + "/" + x.path + "'", alive_files)))
)
print(ddb.sql(query))

print("============= perform query that shows the running count =============")

# Run the query
s1, f1, t1, l1 = log.read_at_max_time(s3c, round(time() * 1000))
alive_files = list(filter(lambda x: x.tombstone is None, f1))
query = ("select user_id, event, sum(cnt) as cnt "
         "from read_parquet([{}]) "
         "group by user_id, event "
         "order by sum(cnt) desc").format(
    ', '.join(list(map(lambda x: "'s3://" + ice.s3c.s3bucket + "/" + x.path + "'", alive_files)))
)
print(ddb.sql(query))

print("============= merging =============")
# here we reduce the rows to a single sum, and we'll keep the latest ts to know when it last updated
merged_log, new_file, partition, merged_files, meta = ice.merge(custom_merge_query="""
select sum(cnt)::INT8 as cnt, max(ts) as ts, user_id, event
from source_files
group by user_id, event
""")
print(f"merged {len(merged_files)} data files from partition {partition}")

print("============= check number of raw rows in data =============")
print("(see it's smaller than the count now because we merged)")

# Run the query
s1, f1, t1, l1 = log.read_at_max_time(s3c, round(time() * 1000))
alive_files = list(filter(lambda x: x.tombstone is None, f1))
query = ("select user_id, count(*) as cnt "
         "from read_parquet([{}]) "
         "group by user_id, event "
         "order by count(user_id) desc").format(
    ', '.join(list(map(lambda x: "'s3://" + ice.s3c.s3bucket + "/" + x.path + "'", alive_files)))
)
print(ddb.sql(query))

print("============= perform query that shows the running count =============")
print("(but we still maintained the running count!)")

# Run the query
s1, f1, t1, l1 = log.read_at_max_time(s3c, round(time() * 1000))
alive_files = list(filter(lambda x: x.tombstone is None, f1))
query = ("select user_id, event, sum(cnt) as cnt "
         "from read_parquet([{}]) "
         "group by user_id, event "
         "order by sum(cnt) desc").format(
    ', '.join(list(map(lambda x: "'s3://" + ice.s3c.s3bucket + "/" + x.path + "'", alive_files)))
)
print(ddb.sql(query))

delete_all_s3(s3c)
