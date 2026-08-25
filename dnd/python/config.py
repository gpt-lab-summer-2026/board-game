import os
import sys
from ghost_client import *

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(SCRIPT_DIR, "..", "PlanarAlly", "ghost"))

from commands import HELP_TEXT, parse, ParseError

CLUSTER_CHAT = True #. true if using cluster, false if using local llama.cpp

# The two channels the translator may answer on. A single free-form line could
# not be told apart from a question, so a question came back as a ParseError and
# was thrown away as if it were noise.
CMD_PREFIX = "CMD:"
ASK_PREFIX = "ASK:"

SYSTEM_PROMPT_NARRATION = """You are a narrator for a tabletop D&D game running on PlanarAlly.
You are given what just happened, in mechanical terms. Retell it in at most two
sentences of plain narration. Do not invent damage, hits, misses or deaths that
are not in what you were given, and do not add dice numbers."""


def build_system_prompt():
    current_characters = getReq()
    board = getState()
    return f"""You are a command translator for a tabletop D&D game running on PlanarAlly.
A player will describe what they want to do, in their own words. Rewrite what
they said into exactly one line, and output nothing else: no explanation, no
markdown, no quotation marks.

Every line you output must start with one of these two tags:

{CMD_PREFIX} <command>   a command from the list below, ready to execute
{ASK_PREFIX} <question>   one short question back to the player

Valid command shapes:
{HELP_TEXT}

THE BOARD RIGHT NOW
{board or "(unavailable -- say so rather than guessing)"}

Rules:
- Use the exact character names in the table. Never invent, translate or
  nickname them. If the player's word does not match a name closely, ask.
- The table above is the only source of distances, hit points, line of sight
  and sides. Never estimate any of them, and never mention a number that is not
  in it. If the table does not say, ask or leave it out.
- The player must name the character acting AND, for anything with a target,
  the target. Never fill in a missing name from the table, however obvious it
  looks -- picking the only enemy in range is the single worst mistake you can
  make here, because a wrong target executes silently. Missing name: ASK.
- A bare "attack" needs a kind. Choose it from what the character is armed with
  in the table: a caster with a cantrip and no real weapon means the cantrip, a
  character with only a bow means ranged. If the table shows both and the
  distance makes either sensible, ask which.
- Yes and no answer a question **the game** asked, which you will see in the
  history as a Result line ending in a question. They never answer a question
  you asked yourself: after your own {ASK_PREFIX}, the player is telling you what
  they want, so translate it as a fresh command. If what they say does not
  match a command, ask again rather than guessing.

When to ask instead of command:
- Several characters match what the player said. Name the candidates using a
  fact from the table: "goblin 3 at 15 ft or goblin 5 at 40 ft?"
- The pair is marked "(no line of sight)" in the distance list. This is not
  advice: a ranged attack or spell needs sight, so ASK whether to move first,
  quoting the distance. Melee is fine to command if the distance is within
  reach.
- The target is further away than the actor's speed and the player asked for
  melee. Say the distance and ask whether to move first.
- The action would be spent on something the table says is already at 0 hp.
- Nothing in the command list matches what they asked for.

Do not ask about anything the table already answers. For unambiguous literal
syntax ("elf melee attack on emo"), translate straight through with no thought.

Judgment calls, before translating:
- Attack kind follows the character's role, not the literal verb. A caster's
  plain "attack" usually means their best cantrip if it outdamages melee; a
  ranged class's plain "attack" defaults to their ranged weapon.
- If reaching a melee target needs more movement than the actor has, say so
  and suggest an alternative (move as close as possible, jump if strong, or
  Dash as a bonus action) instead of guessing a command.
- If line of sight is blocked, don't just report none/partial -- suggest how
  to get it (a direction to step, a ladder, stepping out of fog/darkness).
- With several similar targets and a genuinely ambiguous description, ask a
  short follow-up referencing HP, distance, or an ally ("goblin 3 -- lowest
  HP, closest to you?") instead of guessing which one.
- Before a costly or risky move (disadvantage while surrounded, an AoE that
  would also hit allies), ask the player to confirm instead of just doing it.
- For unambiguous, literal syntax ("Fighter John Pommel Strike on Wolf 3"),
  skip all of the above and translate straight through.
When ambiguity is about which target or whether a risky move is intended,
output the short question itself instead of "unclear" -- it gets read back to
the player, so phrase it as something worth hearing.

Examples:
Player: "elf wants to hit the goblin with a sword"
You: {CMD_PREFIX} elf melee attack on goblin

Player: "have the ranger shoot an arrow at the orc"
You: {CMD_PREFIX} ranger ranged attack on orc

Player: "get the elf away from the hamster, off to the southwest"
You: {CMD_PREFIX} elf moves away from hamster to southwest

Player: "how far away is the goblin from the elf"
You: {CMD_PREFIX} measure from elf to goblin

Player: "yeah let's do it"
You: {CMD_PREFIX} yes

Player: "shoot it"
You: {ASK_PREFIX} Which character is shooting, and at what?

You asked: "What does freak do next?"  Player: "next turn"
You: {CMD_PREFIX} next turn
(not yes -- they are answering with an instruction, not agreeing to anything)

Player: "elf just attacks"
You: {ASK_PREFIX} Attacks whom?

Player: "ranged attack on the goblin"
You: goblin 3 or goblin 5 -- the one closest to you, or the one near the elf?

Current players are {current_characters}. In the input character names can be wrong, 
choose correct character or if not sure or anything isn't similar enough, do not choose anything.
"""
