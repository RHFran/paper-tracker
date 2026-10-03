# Running Paper Tracker on a schedule

These are examples to review and adapt, not installed services. First complete
configuration validation, inspect a real dry run, and test your own sender.
Use a single scheduling approach per configuration and durable state storage.

## Foreground process

From an activated virtual environment with your secrets exported:

```sh
paper-tracker --config /absolute/private/path/config.json schedule --send
```

The process checks each profile's local schedule. Keep it running under a service
manager for unattended use. Without `--send`, it remains a dry-run worker.

The Python module and existing `literature-digest` command remain compatible.
The example service filenames are retained to avoid breaking existing timers.

## systemd (Linux)

Edit `literature-digest.service` to set your unprivileged user, checkout, Python,
private config and environment paths. The service runs `tick --send`; remove
`--send` while rehearsing. The timer checks once a minute, while the application's
profile timezone, weekday and `HH:MM` settings decide what is due.

After reviewing the files, an operator can install them into
`/etc/systemd/system/`, run `systemctl daemon-reload`, then enable and start
`literature-digest.timer`. Inspect `systemctl list-timers` and
`journalctl -u literature-digest.service`. Disabling the timer stops future ticks;
it does not cancel an already-running send.

Keep the environment file private (mode `600`) and state/output paths writable
by the configured user. Do not run the service as root.

## cron

Customize `run-digest-tick.sh` and `crontab.example`, using absolute paths. The
wrapper explicitly loads a private environment file because cron normally has a
minimal environment. Install the example crontab line only after review. A run
outside the configured local time/day does not send; default same-day catch-up
allows a delayed tick to run after the target time.

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

Use host tools with appropriate permissions to inspect generated reports. With
your own private `.env` configured, a foreground production invocation is:

```sh
docker run --rm --env-file .env -v "$PWD/runtime:/data" \
  paper-tracker:local --config /data/config.json schedule --send
```

Or run `docker compose -f examples/compose.yaml up --build` from the repository
root. The compose example is dry-run by default. Add `--send` to its command only
after the real report and sender have been checked, with `mail.enabled: true`.
Create `.env` before using the compose example; it may be empty for a demo.
Docker build/run and real provider connectivity must be verified in your deployment.
