"""
triage_agent.py
AI Clinical Triage Agent using Ollama + Pydantic with a 2-retry validation loop
and a deterministic keyword-based fallback classifier.
"""

from datetime import datetime, timezone
import json
import logging
import os
import re
import time
from typing import Any, Dict, Literal, Optional, Tuple
import ollama
from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger("ems.triage")


class TriageSchema(BaseModel):
    triage_level: int = Field(
        ...,
        ge=1,
        le=5,
        description="Triage level rating from 1 (most critical) to 5 (least critical).",
    )
    equipment_needed: Literal["ICU", "Basic"] = Field(
        ...,
        description="Required equipment classification: strictly 'ICU' or 'Basic'.",
    )
    clinical_summary: str = Field(
        ..., description="Brief summary of clinical assessment and rationale."
    )


def extract_json(text: str) -> str:
    """Extracts JSON payload if wrapped in markdown code blocks or surrounding commentary."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    return match.group(0) if match else text.strip()


def keyword_fallback_triage(patient_notes: str) -> TriageSchema:
    """Deterministic keyword-based triage classifier used when Ollama is unavailable
    or fails Pydantic/JSON validation after retries.
    """
    notes = patient_notes.lower().strip()

    # Level 1: Immediate life-threatening resuscitation (ICU)
    level_1_keywords = (
        "cardiac arrest",
        "heart attack",
        "chest pain",
        "unconscious",
        "unresponsive",
        "not breathing",
        "apnea",
        "severe bleeding",
        "massive bleeding",
        "arterial bleeding",
        "hemorrhage",
        "stroke",
        "anaphylaxis",
        "choking",
        "gunshot",
        "stab wound",
    )
    for kw in level_1_keywords:
        if kw in notes:
            return TriageSchema(
                triage_level=1,
                equipment_needed="ICU",
                clinical_summary=f"Fallback Triage (Level 1 - Critical): Detected '{kw}'. Immediate ICU dispatch required.",
            )

    # Level 2: Emergent / high-risk instability (ICU)
    level_2_keywords = (
        "bleeding",
        "shortness of breath",
        "difficulty breathing",
        "dyspnea",
        "seizure",
        "convulsion",
        "head injury",
        "head trauma",
        "severe burn",
        "syncope",
        "fainting",
        "overdose",
        "poisoning",
    )
    for kw in level_2_keywords:
        if kw in notes:
            return TriageSchema(
                triage_level=2,
                equipment_needed="ICU",
                clinical_summary=f"Fallback Triage (Level 2 - Emergent): Detected '{kw}'. Advanced ICU unit assigned.",
            )

    # Level 3: Urgent stabilization required (Basic)
    level_3_keywords = (
        "fracture",
        "broken bone",
        "dislocation",
        "abdominal pain",
        "high fever",
        "laceration",
        "deep cut",
        "burn",
        "asthma",
        "dehydration",
    )
    for kw in level_3_keywords:
        if kw in notes:
            return TriageSchema(
                triage_level=3,
                equipment_needed="Basic",
                clinical_summary=f"Fallback Triage (Level 3 - Urgent): Detected '{kw}'. Basic ambulance transport assigned.",
            )

    # Level 4: Less urgent acute symptoms (Basic)
    level_4_keywords = (
        "sprain",
        "minor cut",
        "bruise",
        "mild fever",
        "nausea",
        "vomiting",
        "dizziness",
    )
    for kw in level_4_keywords:
        if kw in notes:
            return TriageSchema(
                triage_level=4,
                equipment_needed="Basic",
                clinical_summary=f"Fallback Triage (Level 4 - Less Urgent): Detected '{kw}'. Standard ER evaluation.",
            )

    # Level 5: Non-urgent default
    return TriageSchema(
        triage_level=5,
        equipment_needed="Basic",
        clinical_summary="Fallback Triage (Level 5 - Non-Urgent): No critical keywords detected; routine transport.",
    )


def query_triage_with_meta(
    patient_notes: str,
    host: str = os.getenv("OLLAMA_HOST", "http://localhost:11434"),
    model: str = "llama3.2:1b",
    max_retries: int = 2,
) -> Tuple[TriageSchema, Dict[str, Any]]:
    """Queries Ollama with llama3.2:1b and retries JSON/Pydantic validation up to `max_retries` times.
    Falls back deterministically to `keyword_fallback_triage` upon API or validation failure.

    Returns:
        Tuple of (validated TriageSchema, metadata dict with latency and fallback status).
    """
    start_perf = time.perf_counter()
    client = ollama.Client(host=host)

    system_prompt = (
        "You are an expert clinical triage assistant. Analyze the patient notes and return a JSON object.\n"
        "Required Schema:\n"
        "{\n"
        '  "triage_level": <integer 1 to 5>,\n'
        '  "equipment_needed": "<ICU or Basic>",\n'
        '  "clinical_summary": "<string summary>"\n'
        "}\n"
        "Return ONLY raw valid JSON."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Patient Notes:\n{patient_notes}"},
    ]

    last_error: Optional[Exception] = None

    for attempt in range(1, max_retries + 1):
        raw_text: Optional[str] = None
        try:
            response = client.chat(
                model=model,
                messages=messages,
                format="json",
                options={"temperature": 0.1},
            )

            raw_text = response["message"]["content"]
            json_text = extract_json(raw_text)

            parsed_json = json.loads(json_text)
            validated_triage = TriageSchema.model_validate(parsed_json)

            latency_ms = (time.perf_counter() - start_perf) * 1000.0
            meta = {
                "fallback_used": False,
                "attempts": attempt,
                "triage_latency_ms": round(latency_ms, 3),
                "error": None,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            return validated_triage, meta

        except (json.JSONDecodeError, ValidationError) as err:
            last_error = err
            logger.warning(
                "Triage validation failed on attempt %d/%d: %s",
                attempt,
                max_retries,
                err,
            )
            if raw_text is not None:
                messages.append({"role": "assistant", "content": raw_text})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"Attempt {attempt} failed with validation error: {err}. "
                            "Regenerate the response adhering strictly to the required JSON schema."
                        ),
                    }
                )
        except Exception as api_err:
            last_error = api_err
            logger.warning(
                "Ollama API call failed on attempt %d/%d: %s",
                attempt,
                max_retries,
                api_err,
            )

    # Trigger deterministic keyword fallback after exhausting retries
    fallback_result = keyword_fallback_triage(patient_notes)
    latency_ms = (time.perf_counter() - start_perf) * 1000.0
    logger.warning(
        "Triggering deterministic keyword fallback after %d failed attempts. Last error: %s",
        max_retries,
        last_error,
    )
    meta = {
        "fallback_used": True,
        "attempts": max_retries,
        "triage_latency_ms": round(latency_ms, 3),
        "error": str(last_error) if last_error else "Unknown error",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return fallback_result, meta


def query_triage(
    patient_notes: str,
    host: str = os.getenv("OLLAMA_HOST", "http://localhost:11434"),
    model: str = "llama3.2:1b",
    max_retries: int = 2,
) -> TriageSchema:
    """Convenience wrapper returning the validated `TriageSchema` directly."""
    result, _ = query_triage_with_meta(
        patient_notes=patient_notes,
        host=host,
        model=model,
        max_retries=max_retries,
    )
    return result


if __name__ == "__main__":
    sample_notes = "65yo male presenting with acute chest pain and profuse sweating."
    triage_out, metadata = query_triage_with_meta(sample_notes)
    print("Triage Output:", triage_out.model_dump_json(indent=2))
    print("Execution Metadata:", json.dumps(metadata, indent=2))