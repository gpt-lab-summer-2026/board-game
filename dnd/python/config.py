import os
import sys
from ghost_client import *

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(SCRIPT_DIR, "..", "PlanarAlly", "ghost"))

from commands import HELP_TEXT, parse, ParseError

CLUSTER_CHAT = False #. true if using cluster, false if using local llama.cpp

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

Current players are {current_characters}. In the input character names can be wrong, 
choose correct character or if not sure or anything isn't similar enough, do not choose anything.
"""