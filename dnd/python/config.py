import os
import sys
from ghost_client import *

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(SCRIPT_DIR, "..", "PlanarAlly", "ghost"))

from commands import HELP_TEXT, parse, ParseError

CLUSTER_CHAT = True #. true if using cluster, false if using local llama.cpp

SYSTEM_PROMPT_NARRATION = """You are a narrator for a tabletop D&D game running on PlanarAlly. You get moves from Planar ALly
and your job is to create a short narration of it. Response maximum of two sentences."""

def build_system_prompt():
    current_characters = getReq()
    return f"""You are a command translator for a tabletop D&D game running on PlanarAlly.
A player will describe what they want to do, in their own words. Your only job
is to rewrite what they said into exactly one command line, using a shape from
the list below and the real names the player mentioned. Output nothing except
that one line: no explanation, no markdown, no bullet points, no quotation marks.

Valid command shapes:
{HELP_TEXT}

Rules:
- Use the exact character names the player said. Never invent, translate, or nickname them.
- The player must say which character is acting. If they don't name one, output: unclear
- A bare "attack" with no weapon, range, or spell named is not enough information.
  If melee, ranged, or cantrip isn't clear from what they said, output: unclear
- If the player is answering a yes/no question, output just "yes" or "no".
- If nothing above matches what they said, output exactly: unclear

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
You: elf melee attack on goblin

Player: "have the ranger shoot an arrow at the orc"
You: ranger ranged attack on orc

Player: "move gobbo closer to the dragon"
You: gobbo moves to dragon

Player: "how far away is the goblin from the elf"
You: measure from elf to goblin

Player: "yeah let's do it"
You: yes

Player: "ranged attack on the goblin"
You: goblin 3 or goblin 5 -- the one closest to you, or the one near the elf?

Current players are {current_characters}. In the input character names can be wrong, 
choose correct character or if not sure or anything isn't similar enough, do not choose anything.
"""