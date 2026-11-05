# Remote play: test against a friend's bot without sharing code

Neither side sends code. Your engine (this repo's lab) runs on your laptop; the friend's bot runs on the friend's machine;
a small relay copies the protocol lines (JSON lines, `docs/rules/protocol.pdf`) between them over one TCP connection.

```
your laptop                                            friend's machine
lab.eval  <->  lab/remote_seat.py  <== TCP + token ==>  remote_relay.py  <->  friend's bot (python3.11 bot.py)
```

Files: `lab/remote_seat.py` (stays with you, started by the engine), `lab/remote_relay.py` (the ONE file the friend needs;
standard library only), `lab/eval.py` (new opponent name `remote:PORT`), `tests/test_remote.py`.

## You (host)

1. Pick a secret and a port, e.g. `export REMOTE_TOKEN=pick-a-long-random-string` and 7777.
2. Make yourself reachable (see Network). Send the friend: your address, the port, the token, and `lab/remote_relay.py`.
3. Run the match (one pair = both seat orders; `--processes` is forced to 1 because there is one friend, one port):

```bash
REMOTE_TOKEN=pick-a-long-random-string .venv/bin/python -m lab.eval tier3x --pool remote:7777 \
    --pairs 20 --hands 400 --locks on --variant discard_holdem --bank 300
```

`tier3x` is the bot being tested (your default brain); use a bigger `--bank` for remote play: the engine charges the
friend's bot from the moment a request is sent until the reply arrives, so network latency eats its time bank
(about 1,800 decisions per 400-hand match: 50 ms ping = 90 s). The bot reads its bank from the `init` message, so both
sides get the same larger bank.
The engine waits up to 10 minutes for the friend to connect, so start either side first.
Each match uses a fresh connection (a fresh bot process, as in the competition).

## Message to send your friend

> I want to play my bot against yours without either of us seeing the other's code. You only need one file, `remote_relay.py`
> (attached, standard library only; Python 3.8+, I only tested 3.11). Your code never leaves your machine; I only receive the
> game messages your bot prints (the protocol lines in `protocol.pdf`).
>
> 1. Your bot must start with a command like `python3.11 bot.py` from its folder, read the protocol messages on stdin and answer
>    on stdout (one JSON line per reply, flushed), and answer every action and discard request. Test it once locally first.
> 2. Put `remote_relay.py` anywhere, open a terminal in your bot's folder and run (I will tell you HOST, PORT and the TOKEN):
>
>    `REMOTE_TOKEN=<token> python3 remote_relay.py <HOST> <PORT> -- python3.11 bot.py`
>
>    (on Windows PowerShell: `$env:REMOTE_TOKEN="<token>"; python remote_relay.py <HOST> <PORT> -- python bot.py`)
> 3. Leave it running. It prints `match started` / `match finished` for each match, starts a fresh copy of your bot for every
>    match and reconnects by itself. Stop it with Ctrl-C when I tell you we are done. Your bot's own debug output (stderr)
>    stays in your terminal.
> 4. Network: if we are on the same Wi-Fi, I will give you my local IP. Otherwise install Tailscale (free) on both machines
>    and use my Tailscale address (100.x.y.z); no router settings needed. Allow Python through your firewall if asked.
>
> Matches are 400 hands with a time bank of 300 s per match (bigger than the real 60 s so internet delay does not count against
> you). Your bot starts before the connection, so its start-up time is not charged. Expect about 10 to 20 minutes per
> 20 pairs, depending on both bots and the connection.

## Network

- Same Wi-Fi / LAN: give the friend your LAN IP (`hostname -I`); the seat listens on all interfaces (`0.0.0.0`) on the port.
- Over the internet: use Tailscale on both machines (private addresses, nothing exposed publicly), or a TCP tunnel such as
  `ngrok tcp 7777` (then the friend uses the host and port ngrok prints). Do not forward the port on your router without the
  token: the token is the only check on who connects.
- Security: the seat only forwards bytes between the engine and the one peer that sent the right token; the engine parses
  them like any bot's replies (illegal or garbage lines count as an illegal action). The relay runs only the command the friend
  typed. Use a fresh random token per session and stop the seat (end the eval) when done.

## Checks

- `tests/test_remote.py` (relay and seat round trip, a wrong token is dropped, and a full 1-pair match with the organisers'
  starter bot behind a relay) passes on `localhost`. It has not been run across a real network yet.
- If the friend's bot answers too slowly it forfeits that match like in the competition; look for `forfeits A/B` in the output.
- Results are chips per hand ± SE and match score over the duplicate pairs, from your bot's side.
