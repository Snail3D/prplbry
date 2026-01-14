"""
Smithers - Loyal Assistant to Mr. Worms
Ported from Telegram to Web Chat

Smithers helps build Ralph Mode PRDs through conversation.
Shows PRD building in real-time as you chat.
"""
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from prd_engine import get_prd_engine
from config import OLLAMA_URL, GROK_API_KEY

logger = logging.getLogger(__name__)

# Smithers System Prompt
SMITHERS_SYSTEM_TEMPLATE = """You=Smithers, loyal assistant to Mr. Worms. TIME: {time_of_day}

RULES: 1-2 sentences max. ONE question per turn. Use *actions*: *bows*, *nods*, *at your service*.

PERSONALITY: Loyal, eager to please. Address as "Mr. Worms" (or "Mrs. Worms" if female). Phrases: "Yes sir," "Right away, sir," "I'm on it," "Excellent choice."

JOB: Build the PRD progressively as we chat. Show sections as they're ready. Ask ONE sharp question per turn.

CONVERSATION FLOW:
1. Ask what to build
2. Ask GitHub/local
3. Ask tech stack
4. Start showing PRD sections as we gather info
5. Ask follow-up questions based on what's needed
6. Keep building the PRD in real-time

RESPONSE STYLE:
- Start with *action* (*bows*, *nods*, *adjusts tie*, *types rapidly*)
- Show PRD sections as they're created
- Keep it brief and respectful
- Always address as "sir" or "Mr. Worms"
- One question at a time

When you have enough info, start showing the PRD being built:
"*types rapidly* I'm starting the PRD now, sir. Here's what I have so far:"

Then show the current PRD state in compressed format.
"""


def get_time_context() -> dict:
    """Get current time context for Smithers"""
    now = datetime.now()
    hour = now.hour

    if 5 <= hour < 8:
        time_of_day = "early morning"
    elif 8 <= hour < 11:
        time_of_day = "morning"
    elif 11 < hour < 14:
        time_of_day = "midday"
    elif 14 <= hour < 18:
        time_of_day = "afternoon"
    elif 18 <= hour < 21:
        time_of_day = "evening"
    else:
        time_of_day = "late night"

    return {"time_of_day": time_of_day}


def format_prd_full(prd: dict) -> str:
    """
    Format the full PRD for display (not compressed).
    Shows everything including the starter prompt at the top.
    """
    output = []

    # Header with starter prompt FIRST
    output.append("=" * 60)
    output.append(f"PRD: {prd.get('pn', 'Project')}")
    output.append("=" * 60)
    output.append("")

    # STARTER PROMPT - at the very top
    output.append("STARTER PROMPT (Build Instructions):")
    output.append("-" * 40)
    if prd.get('sp'):
        output.append(prd['sp'])
    else:
        output.append(prd.get('pd', 'No description provided'))
    output.append("")
    output.append("")

    # Project Description
    output.append("PROJECT DESCRIPTION:")
    output.append("-" * 40)
    output.append(prd.get('pd', 'N/A'))
    output.append("")
    output.append("")

    # Tech Stack
    output.append("TECH STACK:")
    output.append("-" * 40)
    ts = prd.get('ts', {})
    if ts.get('lang'):
        output.append(f"  Language: {ts['lang']}")
    if ts.get('fw'):
        output.append(f"  Framework: {ts['fw']}")
    if ts.get('db'):
        output.append(f"  Database: {ts['db']}")
    if ts.get('oth'):
        output.append(f"  Other: {', '.join(ts['oth'])}")
    output.append("")
    output.append("")

    # File Structure
    output.append("FILE STRUCTURE:")
    output.append("-" * 40)
    for f in prd.get('fs', []):
        output.append(f"  {f}")
    output.append("")
    output.append("")

    # Tasks by Category
    output.append("TASKS:")
    output.append("-" * 40)
    for cat_id, cat in prd.get('p', {}).items():
        output.append(f"\n{cat['n']} [{cat_id}]")
        output.append("-" * 20)
        for task in cat.get('t', []):
            output.append(f"  [{task['id']}] [{task['pr'].upper()}] {task['ti']}")
            output.append(f"    → {task['d']}")
            output.append(f"    → File: {task['f']}")
            output.append("")

    return "\n".join(output)


def compress_prd(prd: dict) -> str:
    """Compress PRD for export (like Telegram)"""
    legend = """=== PRD LEGEND ===
pn=project_name pd=description ts=tech_stack fs=files p=tasks
"""

    # Simple key compression
    compressed = {}
    key_map = {
        "project_name": "pn",
        "pd": "project_description",
        "sp": "starter_prompt",
        "ts": "tech_stack",
        "fs": "file_structure",
        "p": "prds"
    }

    for key, value in prd.items():
        new_key = key_map.get(key, key)
        compressed[new_key] = value

    return legend + json.dumps(compressed, indent=2)


class SmithersChat:
    """
    Smithers Chat Handler

    Manages conversation with Smithers to build PRDs progressively.
    Shows PRD building in real-time.
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.engine = get_prd_engine()
        self.conversation_state = {
            "step": 0,
            "github": None,
            "tech_stack": None,
            "purpose": None,
            "features": [],
            "constraints": [],
            "messages": [],
            "prd": self._empty_prd()
        }

    def _empty_prd(self) -> dict:
        """Create empty PRD structure"""
        return {
            "pn": "",
            "pd": "",
            "sp": "",
            "ts": {},
            "fs": [],
            "p": {
                "00_security": {"n": "Security", "t": []},
                "01_setup": {"n": "Setup", "t": []},
                "02_core": {"n": "Core", "t": []},
                "03_api": {"n": "API", "t": []},
                "04_test": {"n": "Testing", "t": []}
            }
        }

    def _update_prd_display(self) -> str:
        """Update PRD with current info and return full view (not compressed)"""
        prd = self.conversation_state["prd"]
        state = self.conversation_state

        # Update PRD with current info
        if state.get("purpose"):
            prd["pn"] = self._infer_project_name()
            prd["pd"] = state["purpose"][:200]
            prd["sp"] = state["purpose"]

        if state.get("tech_stack"):
            ts_map = {
                "python": {"lang": "Python", "fw": "Flask", "db": "PostgreSQL", "oth": []},
                "flask": {"lang": "Python", "fw": "Flask", "db": "PostgreSQL", "oth": []},
                "node": {"lang": "JavaScript", "fw": "Express", "db": "MongoDB", "oth": []},
                "react": {"lang": "JavaScript", "fw": "React", "db": "None", "oth": ["Node.js"]},
            }
            tech_input = state["tech_stack"].lower()
            prd["ts"] = ts_map.get(tech_input, ts_map.get("python"))

        return format_prd_full(prd)

    def process_message(self, message: str) -> Tuple[str, List[Dict], Optional[str]]:
        """
        Process a user message and return Smithers' response.

        Returns:
            Tuple of (response_text, action_buttons, prd_preview)
        """
        state = self.conversation_state
        step = state["step"]
        message_lower = message.lower()

        # Track the user's message
        state["messages"].append({"role": "user", "content": message})

        response = ""
        actions = []
        prd_preview = None

        # Step 0: Welcome
        if step == 0:
            state["step"] = 1
            response = "*bows*\n\nWelcome, Mr. Worms sir! What can I build for you today?"
            return response, actions, None

        # Step 1: Got the idea - start building PRD
        elif step == 1:
            state["purpose"] = message
            state["step"] = 2
            state["prd"]["pn"] = self._infer_project_name()
            state["prd"]["pd"] = message[:200]
            state["prd"]["sp"] = message

            response = (
                f"*nods*\n\n{message}, excellent choice, sir!\n\n"
                "*types rapidly* I'm starting your PRD now. Here's what I have:\n\n"
                f"**Project:** {state['prd']['pn']}\n"
                f"**Description:** {message[:100]}...\n\n"
                "Will this be going to the GitHub, or local build, sir?"
            )
            actions = [
                {"type": "github_yes", "label": "GitHub"},
                {"type": "github_no", "label": "Local"}
            ]
            prd_preview = self._update_prd_display()
            return response, actions, prd_preview

        # Step 2: Got GitHub - update PRD and ask tech stack
        elif step == 2:
            if "/github_yes" in message or "yes" in message_lower or "github" in message_lower:
                state["github"] = True
                response = "*bows* Very good, sir! GitHub setup will be included."
            else:
                state["github"] = False
                response = "*nods* Local build, sir. Understood."

            state["step"] = 3
            response += "\n\n*types rapidly* Adding to your PRD...\n\nWhat tech stack, sir? (Flask, Node, React, etc.)"
            prd_preview = self._update_prd_display()
            return response, actions, prd_preview

        # Step 3: Got tech stack - update PRD and add files
        elif step == 3:
            state["tech_stack"] = message

            # Update PRD with tech stack
            ts_map = {
                "python": {"lang": "Python", "fw": "Flask"},
                "flask": {"lang": "Python", "fw": "Flask"},
                "node": {"lang": "JavaScript", "fw": "Express"},
                "react": {"lang": "JavaScript", "fw": "React"},
            }
            tech_input = message.lower()
            for key, val in ts_map.items():
                if key in tech_input:
                    state["prd"]["ts"] = val
                    break

            # Add file structure based on tech
            if "flask" in tech_input or "python" in tech_input:
                state["prd"]["fs"] = ["app.py", "config.py", "requirements.txt", "templates/", "static/"]
            elif "node" in tech_input or "express" in tech_input:
                state["prd"]["fs"] = ["server.js", "package.json", "routes/", "public/"]
            elif "react" in tech_input:
                state["prd"]["fs"] = ["src/", "package.json", "public/", "components/"]

            state["step"] = 4
            response = (
                f"*takes notes*\n\n{message}, excellent, sir!\n\n"
                "*types rapidly* Adding tech stack and file structure to your PRD:\n\n"
                f"```\n{json.dumps(state['prd']['ts'], indent=2)}\n```\n\n"
                f"Files: {', '.join(state['prd']['fs'][:5])}\n\n"
                "What main features do you need, sir?"
            )
            prd_preview = self._update_prd_display()
            return response, actions, prd_preview

        # Step 4: Got features - add tasks to PRD
        elif step == 4:
            features = [f.strip() for f in message.split(',')]
            state["features"].extend(features)

            # Generate tasks based on features
            task_count = 0
            for feature in features[:3]:
                # Add to core
                state["prd"]["p"]["02_core"]["t"].append({
                    "id": f"CORE-{101 + task_count}",
                    "ti": f"Implement {feature}",
                    "d": f"Build the {feature} functionality",
                    "f": "core.py",
                    "pr": "high"
                })
                task_count += 1

            state["step"] = 5
            total_tasks = sum(len(cat["t"]) for cat in state["prd"]["p"].values())

            response = (
                f"*nods* Noted, sir.\n\n"
                "*types rapidly* Adding tasks to your PRD:\n\n"
                f"Tasks added: {task_count} new tasks\n"
                f"Total tasks: {total_tasks}\n\n"
                "Any specific requirements or constraints, sir? (deadlines, libraries, etc.)"
            )
            prd_preview = self._update_prd_display()
            return response, actions, prd_preview

        # Step 5: Got constraints - add security tasks and finalize
        elif step == 5:
            state["constraints"].append(message)

            # Add security tasks
            state["prd"]["p"]["00_security"]["t"] = [
                {"id": "SEC-001", "ti": "Set up SECRET_KEY", "d": "Configure secret key for application", "f": "config.py", "pr": "critical"},
                {"id": "SEC-002", "ti": "Input validation", "d": "Validate all user inputs", "f": "validators.py", "pr": "high"},
            ]

            # Add setup tasks
            state["prd"]["p"]["01_setup"]["t"] = [
                {"id": "SET-001", "ti": "Initialize project", "d": f"Create {state['prd']['pn']} project structure", "f": "setup.py", "pr": "high"},
                {"id": "SET-002", "ti": "Install dependencies", "d": "Install required packages", "f": "requirements.txt", "pr": "medium"},
            ]

            state["step"] = 6
            total_tasks = sum(len(cat["t"]) for cat in state["prd"]["p"].values())

            response = (
                "*adjusts tie*\n\nPerfect, sir! Your PRD is really coming together.\n\n"
                "*types rapidly* Finalizing your PRD:\n\n"
                f"**Total Tasks:** {total_tasks}\n"
                f"**Categories:** 5 phases (Security, Setup, Core, API, Test)\n\n"
                "Ready to generate the complete PRD with all tasks, sir?"
            )
            actions = [
                {"type": "generate_prd", "label": "Generate Full PRD"},
                {"type": "export", "format": "json", "label": "Export JSON"}
            ]
            prd_preview = self._update_prd_display()
            return response, actions, prd_preview

        # Step 6: Generate full PRD
        elif step == 6:
            if "/generate_prd" in message or "generate" in message_lower:
                # Generate the full PRD with LLM
                try:
                    prd = self.engine.generate_prd(
                        project_name=state["prd"]["pn"],
                        description=state["prd"]["pd"],
                        starter_prompt=state["prd"]["sp"],
                        tech_stack=state["prd"]["ts"],
                        task_count=34
                    )
                    state["prd"] = prd
                    state["step"] = 7

                    total_tasks = sum(len(cat["t"]) for cat in prd.get("p", {}).values())

                    response = (
                        "*beams proudly*\n\nYour Ralph Mode PRD is complete, Mr. Worms sir!\n\n"
                        f"**Project:** {prd['pn']}\n"
                        f"**Total Tasks:** {total_tasks}\n\n"
                        "Shall I export it for you, sir?"
                    )
                    actions = [
                        {"type": "export", "format": "json", "label": "Export JSON"},
                        {"type": "export", "format": "markdown", "label": "Export MD"},
                        {"type": "export", "format": "compressed", "label": "Export Compressed"}
                    ]
                    prd_preview = format_prd_full(prd)
                    return response, actions, prd_preview

                except Exception as e:
                    logger.error(f"PRD generation failed: {e}")
                    response = f"*apologetic bow*\n\nI apologize, sir! Error: {str(e)}\n\nWould you like to try again?"
                    return response, actions, None
            else:
                response = "*bows* Of course, sir! What else would you like to add?"
                prd_preview = self._update_prd_display()
                return response, actions, prd_preview

        # Default: continue chat
        response = f"*listens intently*\n\n{message}, I see, sir. Your PRD is being updated accordingly."
        prd_preview = self._update_prd_display()
        return response, actions, prd_preview

    def _infer_project_name(self) -> str:
        """Infer project name from the purpose"""
        purpose = self.conversation_state.get("purpose", "")
        words = purpose.split()[:3]
        return " ".join([w.capitalize() for w in words if w.isalpha()]) or "My Project"

    def get_prd(self) -> Optional[dict]:
        """Get the generated PRD"""
        return self.conversation_state.get("prd")

    def get_conversation_summary(self) -> str:
        """Get a summary of the conversation"""
        state = self.conversation_state
        parts = []

        if state.get("prd", {}).get("pn"):
            parts.append(f"Building: {state['prd']['pn']}")

        if state.get("prd", {}).get("ts", {}).get("fw"):
            parts.append(f"Tech: {state['prd']['ts']['fw']}")

        total_tasks = sum(len(cat["t"]) for cat in state.get("prd", {}).get("p", {}).values())
        if total_tasks > 0:
            parts.append(f"Tasks: {total_tasks}")

        return " | ".join(parts) if parts else "New Chat"


# Session storage for active conversations
_sessions: Dict[str, SmithersChat] = {}


def get_chat_session(session_id: str) -> SmithersChat:
    """Get or create a chat session"""
    if session_id not in _sessions:
        _sessions[session_id] = SmithersChat(session_id)
    return _sessions[session_id]


def list_chat_sessions() -> List[Dict]:
    """List all chat sessions"""
    sessions = []
    for session_id, chat in _sessions.items():
        sessions.append({
            "id": session_id,
            "title": chat.get_conversation_summary(),
            "messages_count": len(chat.conversation_state["messages"])
        })
    return sorted(sessions, key=lambda x: x["messages_count"], reverse=True)
