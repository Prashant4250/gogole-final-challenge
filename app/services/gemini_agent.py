from __future__ import annotations

import os
import json
import logging
from datetime import datetime
from typing import Optional, Any

import google.generativeai as genai
from google.generativeai.types import RequestOptions

from app.deps import get_store
from app.models import ChatResponse, StadiumStatusResponse

logger = logging.getLogger("crowdflow.gemini_agent")


def run_gemini_agent(
    message: str,
    tenant_id: str,
    stadium_id: str,
    api_key: Optional[str] = None
) -> ChatResponse:
    """
    Runs the AI Agent workflow. If a Gemini API key is provided or present in the environment,
    it executes the request using Gemini's native tool calling. Otherwise, it falls back
    to an intelligent simulated agent.
    """
    # 1. Determine key availability
    key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    
    thoughts: list[str] = []
    store = get_store()

    # 2. Define tools for the agentic workflow
    def get_stadium_status(t_id: str, s_id: str) -> str:
        """
        Retrieves the status of all zones inside a stadium, including occupancy, safe capacity,
        net flow, risk score, severity, recommendations, and applied interventions.
        """
        thoughts.append(f"Calling tool: get_stadium_status(tenant_id='{t_id}', stadium_id='{s_id}')")
        try:
            status = store.get_stadium_status(tenant_id=t_id, stadium_id=s_id)
            # Serialize for the LLM
            zones_data = []
            for z in status.zones:
                zones_data.append({
                    "zone_id": z.zone_id,
                    "occupancy": z.occupancy,
                    "safe_capacity": z.safe_capacity,
                    "occupancy_ratio": f"{z.occupancy_ratio * 100:.1f}%",
                    "net_flow_per_min": z.net_flow_per_min,
                    "risk_score": z.risk_score,
                    "severity": z.severity.value,
                    "recommendations": [r.model_dump() for r in z.recommendations],
                    "applied_interventions": [i.model_dump() for i in z.applied_interventions]
                })
            return json.dumps({
                "tenant_id": t_id,
                "stadium_id": s_id,
                "generated_at": str(status.generated_at),
                "zones": zones_data
            }, default=str)
        except Exception as e:
            thoughts.append(f"Tool error in get_stadium_status: {str(e)}")
            return json.dumps({"error": f"No status found for tenant {t_id} and stadium {s_id}"})

    def get_hot_zones(min_score: float = 0.7) -> str:
        """
        Retrieves a map of all highly saturated or high-risk zones across stadiums.
        """
        thoughts.append(f"Calling tool: get_hot_zones(min_score={min_score})")
        try:
            hot = store.hot_zones(threshold=min_score)
            res = {}
            for k, zones in hot.items():
                res[k] = [
                    {
                        "zone_id": z.zone_id,
                        "risk_score": z.risk_score,
                        "severity": z.severity.value,
                        "occupancy_ratio": z.occupancy_ratio
                    }
                    for z in zones
                ]
            return json.dumps(res, default=str)
        except Exception as e:
            thoughts.append(f"Tool error in get_hot_zones: {str(e)}")
            return json.dumps({"error": str(e)})

    def apply_intervention(t_id: str, s_id: str, zone_id: str, action: str, reason: str) -> str:
        """
        Applies a safety override/intervention to a specific zone, such as 'soft_close_entry',
        'reroute_inbound', or 'activate_incident_command'.
        """
        thoughts.append(
            f"Calling tool: apply_intervention(tenant_id='{t_id}', stadium_id='{s_id}', "
            f"zone_id='{zone_id}', action='{action}', reason='{reason}')"
        )
        try:
            # Normalize zone ID to handle slight model variations
            normalized_zone = zone_id.lower().replace(" ", "-").strip()
            store.apply_intervention(
                tenant_id=t_id,
                stadium_id=s_id,
                zone_id=normalized_zone,
                action=action,
                reason=reason
            )
            return json.dumps({
                "status": "success",
                "message": f"Successfully applied intervention '{action}' on zone '{normalized_zone}'."
            })
        except Exception as e:
            thoughts.append(f"Tool error in apply_intervention: {str(e)}")
            return json.dumps({"status": "error", "message": str(e)})

    if key:
        # Run using Google GenAI SDK (Gemini API)
        try:
            thoughts.append("Initializing Gemini Client with provided API key...")
            genai.configure(api_key=key)
            
            # Use gemini-1.5-flash as the standard fast agent model
            system_instruction = (
                "You are the CrowdFlow Command AI Ops Assistant, an intelligent agent designed to help "
                "stadium operations commanders manage ingress, occupancy risks, and emergency incidents.\n"
                f"The operator dashboard is currently viewing tenant_id: '{tenant_id}' and stadium_id: '{stadium_id}'.\n"
                "You have direct access to tools for querying stadium status, checking hot zones, and applying overrides.\n"
                "IMPORTANT: If the operator requests you to do something (e.g. close a gate, activate command, reroute), "
                "always run the `apply_intervention` tool first, verify the outcome, and report back clearly.\n"
                "If the operator asks about stadium status or occupancy, use `get_stadium_status` with the current tenant and stadium.\n"
                "Present status updates and analysis in a professional, concise, bulleted format suitable for command-center views."
            )

            # Create model with tools
            model = genai.GenerativeModel(
                model_name="gemini-1.5-flash",
                system_instruction=system_instruction,
                tools=[get_stadium_status, get_hot_zones, apply_intervention]
            )

            # Use chat with automatic tool calling enabled
            chat = model.start_chat(enable_automatic_function_calling=True)
            thoughts.append(f"Sending prompt to Gemini: '{message}'")
            
            # Send message with a timeout of 10s
            response = chat.send_message(
                message,
                request_options=RequestOptions(timeout=10.0)
            )
            
            # Ensure the thought log has at least one entry representing Gemini decision
            if not thoughts or len(thoughts) == 1:
                thoughts.append("Gemini responded directly using zero-shot reasoning.")

            return ChatResponse(
                answer=response.text,
                suggested_questions=[
                    "What is the highest risk zone?",
                    "Close the entry for North Gate",
                    "Reroute inbound traffic on North Gate",
                    "Show stadium summary"
                ],
                thoughts=thoughts
            )

        except Exception as e:
            logger.error(f"Gemini API execution failed: {str(e)}")
            thoughts.append(f"Gemini API failure: {str(e)}. Falling back to simulated agent.")
            # Fall through to simulated agent

    # 3. Simulated/Mock Agent Fallback
    thoughts.append("Running in Simulated Agent Mode (configure GEMINI_API_KEY for live LLM operations)")
    prompt_lower = message.lower().strip()

    try:
        status = store.get_stadium_status(tenant_id=tenant_id, stadium_id=stadium_id)
        zones_list = status.zones
    except Exception:
        zones_list = []

    # Simulation matching logic
    if any(tok in prompt_lower for tok in ["close", "block", "shut", "reroute", "activate", "intervention", "apply"]):
        # Detect zone and action
        detected_zone = "north-gate" # Default fallback
        for z in zones_list:
            if z.zone_id.lower() in prompt_lower:
                detected_zone = z.zone_id
                break

        action = "soft_close_entry"
        if "reroute" in prompt_lower:
            action = "reroute_inbound"
        elif "activate" in prompt_lower or "command" in prompt_lower:
            action = "activate_incident_command"

        # Execute simulated tool
        tool_res = apply_intervention(tenant_id, stadium_id, detected_zone, action, f"Operator requested: '{message}'")
        tool_res_dict = json.loads(tool_res)

        if tool_res_dict.get("status") == "success":
            answer = (
                f"🤖 **[Simulated Agent]** I've applied a safety override on **{detected_zone}**.\n\n"
                f"- **Intervention**: `{action}`\n"
                f"- **Reason**: Operator prompt '{message}'\n\n"
                "The dashboard will reflect this applied intervention immediately on the next refresh."
            )
        else:
            answer = f"🤖 **[Simulated Agent]** Failed to apply override on **{detected_zone}**: {tool_res_dict.get('message')}"

    elif any(tok in prompt_lower for tok in ["highest", "risk", "top", "danger"]):
        # Simulate status query
        status_res = get_stadium_status(tenant_id, stadium_id)
        status_data = json.loads(status_res)
        
        if "error" not in status_data and status_data.get("zones"):
            highest = status_data["zones"][0]
            answer = (
                f"🤖 **[Simulated Agent]** Highest current risk is **{highest['zone_id']}**.\n\n"
                f"- **Risk Score**: `{highest['risk_score']}`\n"
                f"- **Severity**: `{highest['severity'].upper()}`\n"
                f"- **Occupancy**: {highest['occupancy']} / {highest['safe_capacity']} ({highest['occupancy_ratio']})\n"
                f"- **Flow Rate**: {highest['net_flow_per_min']}/min\n"
                f"- **Recommendations**: {', '.join([r['action'] for r in highest['recommendations']]) or 'None'}"
            )
        else:
            answer = "🤖 **[Simulated Agent]** No active high-risk zones detected or stadium signals are not loaded."

    elif any(tok in prompt_lower for tok in ["summary", "stadium", "overview", "status", "occupancy"]):
        status_res = get_stadium_status(tenant_id, stadium_id)
        status_data = json.loads(status_res)

        if "error" not in status_data and status_data.get("zones"):
            total_occ = sum(int(z["occupancy"]) for z in status_data["zones"])
            total_cap = sum(int(z["safe_capacity"]) for z in status_data["zones"])
            highest_zone = status_data["zones"][0]
            
            answer = (
                f"🤖 **[Simulated Agent]** Here is a summary of the stadium operations:\n\n"
                f"- **Total Occupancy**: {total_occ} / {total_cap} ({total_occ/total_cap*100:.1f}%)\n"
                f"- **Active Zones**: {len(status_data['zones'])}\n"
                f"- **Highest Saturation**: **{highest_zone['zone_id']}** ({highest_zone['severity'].upper()} risk)\n"
                f"- **Active Interventions**: {sum(len(z.get('applied_interventions', [])) for z in status_data['zones'])} override(s) active\n\n"
                "Let me know if you would like me to apply any specific crowd routing or gates closure overrides."
            )
        else:
            answer = "🤖 **[Simulated Agent]** Stadium data is currently empty. Please click 'Load demo surge' to populate signals."

    else:
        answer = (
            f"🤖 **[Simulated Agent]** I received your query: '{message}'.\n\n"
            "You can ask me to:\n"
            "1. **Summarize** stadium status ('Show stadium summary')\n"
            "2. **Find risk hotspots** ('What is the highest risk zone?')\n"
            "3. **Apply interventions** ('Close the entry for North Gate' or 'Reroute traffic on North Gate')\n\n"
            "*Configure your `GEMINI_API_KEY` in the top settings panel to enable live LLM reasoning.*"
        )

    return ChatResponse(
        answer=answer,
        suggested_questions=[
            "What is the highest risk zone?",
            "Close the entry for North Gate",
            "Reroute inbound traffic on North Gate",
            "Show stadium summary"
        ],
        thoughts=thoughts
    )
