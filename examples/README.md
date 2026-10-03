# Running Super Paper radar on a schedule

These are examples to review and adapt, not installed services. First complete
configuration validation, inspect a real dry run, and test your own sender.
Use a single scheduling approach per configuration and durable state storage.

## Choose recurring weekdays or specific dates

Use [`config.calendar.example.json`](../config.calendar.example.json) as a safe
starting point for several topic schedules sent to the same inbox. It uses three
unique profile IDs: BVOCs every Monday at 08:30, tree-species remote sensing every
Wednesday at 09:00, and urban forests only on `2027-03-15` at 10:00, all in
`Asia/Shanghai`. Replace the example recipient, topics and future date before use.
Email is disabled in the example. New examples select the full agent workflow;
`run`/`tick` can consume account usage once a CLI is available. Select the correct
agent and review costs before live work; offline `preview` makes no model calls.
See [agent workflow](../docs/agent-workflow.md) for host/connector scheduling.

- `schedule.weekdays`: nonempty unique integers, `0=Monday` through `6=Sunday`.
- `schedule.dates`: nonempty unique valid `YYYY-MM-DD` strings, interpreted in the
  profile's timezone and run only on those dates, without annual recurrence.
- Supply only one selector per schedule object. A profile's explicit `dates`
  replaces inherited weekdays; explicit `weekdays` clears inherited dates.
- `catch_up: true` permits late execution on the same local day only. It does not
  replay a one-off date missed while the host was offline. With `false`, ticks
  must arrive during the scheduled minute.

Copy to a private config and run `validate` to inspect the next scheduled instant
for each profile. An exhausted date list reports `next_run: null`; same-day
catch-up can still apply after today's planned time. Keep the worker running or
install an external minute timer. A JSON file alone does not start a service.
Use `tick`/`schedule` for timed operation: `run` deliberately ignores the schedule.

See the [English guide](../docs/user-guide.md#different-topics-on-different-days) or
[中文说明](../docs/user-guide_中文.md#topic-calendar-zh) for the full setup and inheritance rules.

## Foreground process

From the source checkout, with your private wizard-format environment file:

```sh
bash scripts/run.sh --env-file /absolute/private/path/.env \
  --config /absolute/private/path/config.json schedule --send
```

The process checks each profile's local schedule. Keep it running under a service
manager for unattended use. Without `--send`, it remains a dry-run worker.

The Python module and existing `literature-digest` command remain compatible.
The example service filenames are retained to avoid breaking existing timers.

## systemd (Linux)

Edit `literature-digest.service` to set your unprivileged user, checkout, Python,
private config and environment paths. It calls `.venv/bin/python scripts/launch.py`
with explicit `--env-file` and `--config` paths, then `tick --send`; it does not
use shell sourcing or systemd `EnvironmentFile`. Remove `--send` while rehearsing. The timer checks once a minute, while the application's
profile timezone, weekday/date selection and `HH:MM` settings decide what is due.

After reviewing the files, an operator can install them into
`/etc/systemd/system/`, run `systemctl daemon-reload`, then enable and start
`literature-digest.timer`. Inspect `systemctl list-timers` and
`journalctl -u literature-digest.service`. Disabling the timer stops future ticks;
it does not cancel an already-running send.

Keep the environment file private (mode `600`) and state/output paths writable
by the configured user. Do not run the service as root.

## cron

Customize `run-digest-tick.sh` and `crontab.example`, using absolute paths. The
wrapper uses the application to parse a private environment file as literal data
because cron normally has a minimal environment. Do not source the wizard
`.env` as a shell script. Install the example crontab line only after review. A run
before the configured time or outside a selected local weekday/date does not send;
default same-day catch-up allows a delayed tick to run after the target time.

## Docker

The image runs as UID/GID `10001`, with only standard-library Python runtime code.
The OS timezone database and CA certificates are installed in the image. `/data`
must hold the config, state and output; do not keep state in a disposable container.

```sh
docker build -t paper-tracker:local .
mkdir -p runtime
cp config.example.json runtime/config.json
# Edit runtime/config.json; its relative state/output paths remain under /data.
# Give UID/GID 10001 access to this dedicated directory on a Linux host.
sudo chown -R 10001:10001 runtime
chmod 700 runtime

docker run --rm -v "$PWD/runtime:/data" paper-tracker:local \
  --config /data/config.json validate
docker run --rm -v "$PWD/runtime:/data" paper-tracker:local \
  --config /data/config.json preview --language en
```

Use host tools with appropriate permissions to inspect generated reports. Prepare
a **separate private `runtime/docker.env`** for Docker, using unquoted `KEY=value`
lines. Docker's parser is different from the launcher's: do not pass the wizard's
quoted `.env` directly to Docker or Compose. Do not commit either file. Use your
actual environment names from the config, enable the required model, and make
sure UID/GID `10001` can read only the runtime files it needs. A foreground
production invocation is:

```sh
docker run --rm --env-file runtime/docker.env -v "$PWD/runtime:/data" \
  paper-tracker:local --config /data/config.json schedule --send
```

If you want to reuse a private wizard-format file instead, place it at
`runtime/.env` with access restricted to the intended operator/container UID,
and use the **application's** `--env-file` after the image name. This uses the
same safe literal parser as the launcher, with no shell evaluation:

```sh
docker run --rm -v "$PWD/runtime:/data" paper-tracker:local \
  --env-file /data/.env --config /data/config.json schedule --send
```

Do not combine the two environment-file formats. A wizard `.env` saved with mode
`0600` must have the correct owner for UID `10001`; do not make secrets world-readable.

Or run `docker compose -f examples/compose.yaml up --build` from the repository
root. The compose example is dry-run by default. Add `--send` to its command only
after the real report and sender have been checked, with `mail.enabled: true`.
Create `runtime/docker.env` before using the compose example; it may be empty
only for an offline `preview` command. Real scheduled digests require model
configuration and credentials even when `--send` is absent.
Docker build/run and real provider connectivity must be verified in your deployment.
