# Restore point — a working demo

Snapshot of the state that was verified working on **2026-08-19**, taken before
starting on turn control, rests, reactions and concentration.

Everything here has been checked: the ghost modules compile, the database passes
`integrity_check`, the `.pam` unzips to the right version, and the whole restore
was rehearsed into a scratch tree (see *Rehearsal* below).

## What is in here

| directory | contents | restores to |
|---|---|---|
| `ghost/` | 27 modules | `PlanarAlly/ghost/` |
| `mod/` | `simple-char-sheet.pam` **v0.19.0** | upload + link via the ghost |
| `client/vite/` | 326 files, 11 MB — the built bundle | `PlanarAlly/server/static/vite/` |
| `client/index.html` | the template the bundle needs | `PlanarAlly/server/templates/index.html` |
| `db/planar.sqlite` | 14 shapes, 7 sheets, 5 room blocks | `PlanarAlly/server/data/planar.sqlite` |
| `voice/` | the ghost's TTS package | `dnd/voice/` |
| `python/` | `config.py`, `pipeline.py`, `guard.py`, `ghost_client.py`, `requirements.txt` | `dnd/python/` |

**`main.py` and `listen.py` are deliberately absent.** They are yours and are
edited elsewhere; a restore must not stamp on them. `speak.py` *is* included but
treat it as reference only — it is also yours and may have moved on since.

## Restoring

Stop both processes first. Copying a client bundle or a database under a running
server gives you a half-restored tree that is worse than either state.

```bash
cd ~/board-game/dnd
pkill -f "python -m ghost$"                  # note the $ — without it the
                                             # pattern matches its own shell
pkill -f planarally.py

cp    demo-restore/ghost/*.py            PlanarAlly/ghost/
rm -rf PlanarAlly/server/static/vite
cp -r demo-restore/client/vite           PlanarAlly/server/static/vite
cp    demo-restore/client/index.html     PlanarAlly/server/templates/index.html
cp    demo-restore/db/planar.sqlite      PlanarAlly/server/data/planar.sqlite
rm -f PlanarAlly/server/data/planar.sqlite-wal PlanarAlly/server/data/planar.sqlite-shm
cp    demo-restore/voice/*.py            voice/
cp    demo-restore/python/*.py           python/     # SKIP speak.py if yours differs
```

Deleting the stale `-wal` and `-shm` matters: SQLite will replay a leftover
write-ahead log over the restored database and undo part of the restore. Delete
them **only** with the server stopped — removing a live WAL discards
uncheckpointed transactions, which is how the ghost's password was lost earlier
today.

Then start again:

```bash
cd ~/board-game/dnd/PlanarAlly/server && uv run planarally.py &
cd ~/board-game/dnd/PlanarAlly && setsid nohup server/.venv/bin/python -m ghost \
    >> /tmp/ghost-console.log 2>&1 < /dev/null &
```

The mod is linked by hash, so a restored database already points at v0.19.0 and
needs no re-upload. If it somehow does not, re-link with the installer script.

## Proving the restore worked

```bash
curl -s http://127.0.0.1:8770/characters
# expects: cat, elf, emo, freak, gentelman, hamster, weirdo

curl -s -X POST http://127.0.0.1:8770/command \
     -H 'Content-Type: application/json' \
     -d '{"command":"measure from elf to cat","source":"text"}'
# a distance and a line-of-sight verdict means the socket, the board, the grid
# and the command path are all alive
```

If the first returns seven names and the second a distance, the demo is back.

## Rehearsal

The restore was rehearsed into a scratch tree rather than over the live one, so
the running demo was never taken down to test it. That covers the file
operations and the artefact integrity; it does not cover the server starting
against the restored database, which only a real restore exercises.
