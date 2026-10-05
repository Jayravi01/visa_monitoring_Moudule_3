"""Create the Athena table over the S3 JSON Lines data, plus two Tableau/Power BI-friendly views.

    python athena_setup.py        # create database, table, views and print a sanity check

The table uses partition projection on `dt`, so new daily folders are picked up
automatically (no MSCK REPAIR TABLE needed).

Views (point Tableau or Power BI at these, not the raw table):
    v_visa_changes              one row per change; dates typed; lists joined with '; '
    v_visa_changes_by_category  one row per change x visa category (for visa-type filters and frequency charts)
"""
import time

import boto3
import pandas as pd

import config

DB, TABLE = config.ATHENA_DATABASE, config.ATHENA_TABLE

CREATE_DB = f"CREATE DATABASE IF NOT EXISTS {DB}"

CREATE_TABLE = f"""
CREATE EXTERNAL TABLE IF NOT EXISTS {DB}.{TABLE} (
    id               string,
    source_id        string,
    source_name      string,
    org_type         string,
    title            string,
    summary          string,
    url              string,
    published_date   string,
    effective_date   string,
    change_types     array<string>,
    visa_categories  array<string>,
    products_affected array<string>,
    impact           string,
    impact_score     int,
    impact_rationale string,
    is_sample        boolean,
    first_seen       string
)
PARTITIONED BY (dt string)
ROW FORMAT SERDE 'org.openx.data.jsonserde.JsonSerDe'
WITH SERDEPROPERTIES ('ignore.malformed.json' = 'true')
LOCATION 's3://{config.S3_BUCKET}/{config.S3_PREFIX}/'
TBLPROPERTIES (
    'projection.enabled'            = 'true',
    'projection.dt.type'            = 'date',
    'projection.dt.format'          = 'yyyy-MM-dd',
    'projection.dt.range'           = '2024-01-01,NOW',
    'storage.location.template'     = 's3://{config.S3_BUCKET}/{config.S3_PREFIX}/dt=${{dt}}/'
)
"""

CREATE_VIEW_FLAT = f"""
CREATE OR REPLACE VIEW {DB}.v_visa_changes AS
SELECT id, source_id, source_name, org_type, title, summary, url,
       TRY(CAST(published_date AS date)) AS published_date,
       TRY(CAST(effective_date AS date)) AS effective_date,
       array_join(change_types, '; ')      AS change_types,
       array_join(visa_categories, '; ')   AS visa_categories,
       array_join(products_affected, '; ') AS products_affected,
       impact, impact_score, impact_rationale, is_sample, first_seen, dt
FROM {DB}.{TABLE}
"""

CREATE_VIEW_LONG = f"""
CREATE OR REPLACE VIEW {DB}.v_visa_changes_by_category AS
SELECT c.id, c.source_id, c.source_name, c.title, c.summary, c.url,
       TRY(CAST(c.published_date AS date)) AS published_date,
       TRY(CAST(c.effective_date AS date)) AS effective_date,
       array_join(c.change_types, '; ')      AS change_types,
       array_join(c.products_affected, '; ') AS products_affected,
       c.impact, c.impact_score, t.visa_category
FROM {DB}.{TABLE} c
CROSS JOIN UNNEST(c.visa_categories) AS t(visa_category)
"""


def run_query(sql: str, timeout: int = 120) -> pd.DataFrame:
    """Run SQL on Athena and return a DataFrame (all columns as strings)."""
    athena = boto3.client("athena", region_name=config.REGION)
    qid = athena.start_query_execution(
        QueryString=sql,
        WorkGroup=config.ATHENA_WORKGROUP,
        ResultConfiguration={"OutputLocation": config.ATHENA_OUTPUT},
    )["QueryExecutionId"]

    start = time.time()
    while True:
        status = athena.get_query_execution(QueryExecutionId=qid)["QueryExecution"]["Status"]
        if status["State"] in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
        if time.time() - start > timeout:
            raise TimeoutError(f"Athena query {qid} timed out")
        time.sleep(1)
    if status["State"] != "SUCCEEDED":
        raise RuntimeError(f"Athena query {status['State']}: {status.get('StateChangeReason', '')}")

    rows, token = [], None
    while True:
        kwargs = {"QueryExecutionId": qid, "MaxResults": 1000}
        if token:
            kwargs["NextToken"] = token
        page = athena.get_query_results(**kwargs)
        rows.extend(page["ResultSet"]["Rows"])
        token = page.get("NextToken")
        if not token:
            break
    if not rows:
        return pd.DataFrame()
    header = [c.get("VarCharValue") for c in rows[0]["Data"]]
    data = [[c.get("VarCharValue") for c in r["Data"]] for r in rows[1:]]
    return pd.DataFrame(data, columns=header)


def setup() -> None:
    config.require_aws_settings()
    for label, sql in [
        ("database", CREATE_DB),
        ("table", CREATE_TABLE),
        ("view v_visa_changes", CREATE_VIEW_FLAT),
        ("view v_visa_changes_by_category", CREATE_VIEW_LONG),
    ]:
        run_query(sql)
        print(f"Ready: {label}")

    check = run_query(f"SELECT impact, count(*) AS changes FROM {DB}.v_visa_changes GROUP BY impact ORDER BY 2 DESC")
    print("Sanity check (changes by impact):")
    print(check.to_string(index=False) if not check.empty else "  no rows yet - run the pipeline with live data first")


if __name__ == "__main__":
    setup()
