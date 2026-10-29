#!/usr/bin/env python3
"""Report a Slurm site's GPU allocation to the hub, as the site's accounting reports it.

    quota_collector.py --env deploy/quota.env [--dry-run]

Some of our GPUs are on a shared supercomputer rather than machines of our own: there we
cannot (and should not) watch the devices, but the lab does need to know how much of the
contract is left and who used it. This reads that from the site's accounting tool and
posts it to the hub's /api/v1/quota once per run. It is meant to be run from cron every
ten minutes, not kept running: login-node processes do not survive a reboot, and a cron
entry does.

Only KISTI's ISAM is supported for now. Its numbers -- not Slurm's -- are the ones the
contract is billed against: Slurm on that site enforces no limit, decays its own usage
with a 7-day half-life, and with PrivateData set it will not show one user another's
jobs. ISAM shows the whole account, per user, but only through the previous day.

Runs on the site's system python, which is 3.6 on KISTI, so this file sticks to the
standard library and to syntax 3.6 accepts.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

# Menu 1, "슈퍼컴퓨터 총 SRU-Time 사용량", then quit. ISAM reads its menu choices from stdin
# and needs no TTY; the leading newline dismisses the banner screen.
ISAM_MENU_1 = "\n1\n\nx\n"

ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
NUMBER = r"([\d,]+)"


class ParseError(Exception):
    pass


def to_int(text):
    return int(text.replace(",", ""))


def parse_isam_menu_1(raw):
    """Pull the contract, the total and the per-user rows out of ISAM's menu-1 screen.

    Every figure is in ISAM's "SRU-Time" seconds. Users without any usage get no row at
    all, so the caller fills in known members at zero.
    """
    text = ANSI.sub("", raw)
    # The stream is several screens (banner, menu, menu 1, menu again); work on the one
    # that has the usage table.
    start = text.find("SRU-Time 사용량")
    if start < 0:
        raise ParseError("ISAM output has no 'SRU-Time 사용량' screen")
    screen = text[start:]

    def find(pattern, what):
        match = re.search(pattern, screen)
        if not match:
            raise ParseError("could not find %s in ISAM output" % what)
        return match

    account = find(r"계\s*정\s*:\s*(\S+)", "the account").group(1)
    period = find(r"계약일자\s*:\s*(\d{4}/\d\d/\d\d)\s*-\s*(\d{4}/\d\d/\d\d)", "the contract period")
    # "계약 시간(A) + 보너스(B) + 보상(C) + 이월 = 총사용가능시간(T)": T is what can be spent.
    available = to_int(find(r"=\s*" + NUMBER + r"\s*초", "the total available time").group(1))
    used = to_int(find(r"총사용시간\(SRU-Time\)\s*:\s*" + NUMBER + r"\s*초", "the total used").group(1))

    users = []
    lines = screen.splitlines()
    header = next((i for i, line in enumerate(lines) if "(Host)" in line), None)
    if header is None:
        raise ParseError("could not find the per-user table in ISAM output")
    # Rows are "<user>  <one column per system>  <합계>", between dashed rules, and the
    # table ends with the account's own 합계 row. The last column is the user's total
    # across every system, which is what the contract counts.
    for line in lines[header + 1:]:
        fields = line.split()
        if not fields or set(line.strip()) <= set("-"):
            continue
        if fields[0] == "합계":
            break
        if len(fields) >= 2 and all(re.match(r"^[\d,]+$", f) for f in fields[1:]):
            users.append({"user": fields[0], "used_s": to_int(fields[-1])})
        else:
            break

    return {
        "account": account,
        "period_start": period.group(1).replace("/", "-"),
        "period_end": period.group(2).replace("/", "-"),
        "contract_s": available,
        "used_s": used,
        "users": users,
    }


def read_env(path):
    values = {}
    with open(path) as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip().strip("'\"")
    return values


def run_isam(command):
    proc = subprocess.run(
        [command],
        input=ISAM_MENU_1.encode(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=120,
    )
    if proc.returncode != 0:
        raise ParseError("%s exited with %d" % (command, proc.returncode))
    return proc.stdout.decode("utf-8", "replace")


def post(url, token, payload):
    request = urllib.request.Request(
        url.rstrip("/") + "/api/v1/quota",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + token},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode())


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--env", required=True, help="settings file, see deploy/quota.env.example")
    parser.add_argument("--dry-run", action="store_true", help="print the report instead of posting it")
    args = parser.parse_args()

    env = read_env(args.env)
    here = os.path.dirname(os.path.abspath(args.env))
    # The last good reading, so a failed ISAM call reports the error without blanking
    # the figures on the dashboard.
    last_path = env.get("GPU_QUOTA_LAST_FILE") or os.path.join(here, "..", ".run", "quota-last.json")

    report = {
        "cluster": env.get("GPU_QUOTA_CLUSTER", "slurm"),
        "label": env.get("GPU_QUOTA_LABEL", ""),
        "source": "KISTI ISAM",
        "unit": env.get("GPU_QUOTA_UNIT", "node"),
        "gpus_per_node": int(env.get("GPU_QUOTA_GPUS_PER_NODE", "1")),
        "ts": time.time(),
        "error": None,
    }

    try:
        reading = parse_isam_menu_1(run_isam(env.get("GPU_QUOTA_ISAM", "isam")))
        reading["source_ts"] = report["ts"]
        try:
            os.makedirs(os.path.dirname(last_path), exist_ok=True)
            with open(last_path, "w") as handle:
                json.dump(reading, handle)
        except OSError:
            pass
    except Exception as exc:
        report["error"] = "could not read ISAM: %s" % exc
        try:
            with open(last_path) as handle:
                reading = json.load(handle)
        except (OSError, ValueError):
            reading = {}

    report.update(reading)

    # ISAM only lists users who have spent something; show the rest of the group at zero
    # so a member with no jobs yet does not look like someone we forgot.
    listed = {user["user"] for user in report.get("users", [])}
    for member in filter(None, (m.strip() for m in env.get("GPU_QUOTA_MEMBERS", "").split(","))):
        if member not in listed:
            report.setdefault("users", []).append({"user": member, "used_s": 0})

    if args.dry_run:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    try:
        post(env["GPU_QUOTA_HUB_URL"], env["GPU_QUOTA_TOKEN"], report)
    except urllib.error.HTTPError as exc:
        print("%s push failed: HTTP %d %s" % (time.strftime("%F %T"), exc.code, exc.read()[:200]), file=sys.stderr)
        return 1
    except Exception as exc:
        print("%s push failed: %s" % (time.strftime("%F %T"), exc), file=sys.stderr)
        return 1

    if report["error"]:
        print("%s %s" % (time.strftime("%F %T"), report["error"]), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
