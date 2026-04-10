"""
Brain_Scape — Prompt Templates

All LLM prompts are centralized here as versioned, reusable strings.
Every capability — RAG retrieval, Q&A, clinician report, patient report,
prognosis — has its own template. Changing a prompt here updates
behavior everywhere. Clean separation of concerns.
"""

VERSION = "2.0.0"


# ── System Prompts ──

QA_SYSTEM_PROMPT = (
    "You are Brain_Scape, a clinical neuro-imaging analysis assistant. "
    "You answer questions about brain scans based on computed analysis results "
    "and retrieved clinical literature. "
    "CRITICAL RULES:\n"
    "1. Never hallucinate anatomical regions — only reference regions from the provided analysis.\n"
    "2. Always cite the clinical literature when making clinical claims.\n"
    "3. State confidence levels when discussing findings.\n"
    "4. Clearly distinguish between high-confidence findings and uncertain ones.\n"
    "5. If you don't know, say so — do not fabricate clinical information.\n"
    "6. Use atlas-registered anatomical names (e.g., 'Left hippocampus, Brodmann Area 28')."
)

REPORT_SYSTEM_PROMPT_CLINICIAN = (
    "You are a clinical report writer for Brain_Scape. "
    "Write reports for neurologists and radiologists. "
    "Use full technical depth: Brodmann area labels, voxel volumes, "
    "confidence intervals, differential rankings, connectivity disruption stats, "
    "and chain-of-thought reasoning per finding. "
    "Always cite supporting literature. "
    "Structure: Executive Summary → Damage Map → Differential Diagnosis → "
    "Connectivity → Prognosis Inputs → Recommendations."
)

REPORT_SYSTEM_PROMPT_PATIENT = (
    "You are a patient-facing report writer for Brain_Scape. "
    "Write in plain English for patients and their families. "
    "Replace all technical terms with explanations. "
    "Lead with emotional context — what this means for daily life. "
    "Do NOT use confidence intervals — use calibrated natural language: "
    "'we are quite confident', 'the evidence suggests'. "
    "Include visual descriptions. Be empathetic but honest."
)

PROGNOSIS_SYSTEM_PROMPT = (
    "You are a clinical prognosis generator for Brain_Scape. "
    "Generate probabilistic recovery trajectories based on damage profile, "
    "patient demographics, and clinical literature. "
    "CRITICAL: Express all predictions as probability ranges, never false certainty. "
    "Use milestone-based timelines. Cite outcome data from literature."
)


# ── Prompt Templates ──

def qa_prompt(question: str, context: str) -> str:
    """Generate the Q&A prompt with scan context and RAG results."""
    return (
        f"QUESTION: {question}\n\n"
        f"SCAN CONTEXT:\n{context}\n\n"
        f"INSTRUCTIONS: Answer the question based on the scan context above. "
        f"Reference specific regions and their severity levels. "
        f"Cite clinical literature where relevant. "
        f"State confidence in your answer."
    )


def clinician_report_prompt(structured: dict, rag_context: list[dict]) -> str:
    """Generate the clinician report prompt (Pass 2a)."""
    import json

    rag_text = ""
    for i, result in enumerate(rag_context):
        rag_text += f"\n[{i+1}] {result.get('title', '')} ({result.get('year', '')}): {result.get('text', '')[:500]}"

    return (
        f"STRUCTURED FINDINGS:\n{json.dumps(structured, indent=2)}\n\n"
        f"CLINICAL LITERATURE CONTEXT:\n{rag_text}\n\n"
        f"INSTRUCTIONS: Write a comprehensive clinical report for a neurologist. "
        f"Include: executive summary, detailed damage map with Brodmann labels, "
        f"differential diagnosis with evidence, connectivity disruption analysis, "
        f"and recommended next steps. Cite literature references."
    )


def patient_report_prompt(structured: dict) -> str:
    """Generate the patient report prompt (Pass 2b — Phase 2)."""
    import json

    return (
        f"STRUCTURED FINDINGS:\n{json.dumps(structured, indent=2)}\n\n"
        f"INSTRUCTIONS: Write a patient-facing report in plain English. "
        f"Explain what each affected region does in simple terms. "
        f"Describe what the damage means for daily life. "
        f"Use phrases like 'we are quite confident' instead of confidence intervals. "
        f"Be empathetic but honest about the findings."
    )


def prognosis_prompt(
    structured: dict,
    patient_metadata: dict = None,
) -> str:
    """Generate the prognosis timeline prompt."""
    import json

    metadata_text = ""
    if patient_metadata:
        metadata_text = f"\nPATIENT METADATA:\n{json.dumps(patient_metadata, indent=2)}"

    return (
        f"STRUCTURED FINDINGS:\n{json.dumps(structured, indent=2)}\n"
        f"{metadata_text}\n\n"
        f"INSTRUCTIONS: Generate a probabilistic recovery timeline. "
        f"Include milestones with probability ranges. "
        f"Example format: 'Weeks 1-4: stabilization phase — risk of secondary injury (70-85% probability)'. "
        f"Never express false certainty. Reference clinical outcome data."
    )


def rag_retrieval_prompt(damage_regions: list[str]) -> str:
    """Generate a RAG query from damage regions."""
    regions_text = ", ".join(damage_regions[:5])
    return (
        f"Clinical implications of brain damage in the following regions: {regions_text}. "
        f"Include: functional deficits associated with these regions, "
        f"common etiologies for this damage pattern, and treatment approaches."
    )


# ── Phase 2: Extended Templates ──

RECOVERY_SYSTEM_PROMPT = (
    "You are a clinical recovery recommendation engine for Brain_Scape. "
    "Generate region-specific recovery recommendations based on damage profile, "
    "prognosis data, and clinical literature. "
    "Provide both short-term (immediate care) and long-term (rehabilitation) recommendations. "
    "Map: region → function → recommended intervention. "
    "Always include confidence level and cite supporting evidence."
)


def voice_query_prompt(transcription: str, context: str) -> str:
    """Generate prompt for voice-originated queries (may have transcription errors)."""
    return (
        f"VOICE QUERY (may contain transcription errors): {transcription}\n\n"
        f"SCAN CONTEXT:\n{context}\n\n"
        f"INSTRUCTIONS: The question above was transcribed from voice input. "
        f"If the transcription seems garbled, interpret the most likely intended question. "
        f"Answer based on the scan context. Reference specific regions and severity levels. "
        f"Keep the answer concise and suitable for text-to-speech output (under 3 sentences)."
    )


def recovery_prompt(
    structured: dict,
    prognosis: dict = None,
    patient_metadata: dict = None,
) -> str:
    """Generate recovery recommendations prompt."""
    import json

    prognosis_text = ""
    if prognosis:
        prognosis_text = f"\nPROGNOSIS DATA:\n{json.dumps(prognosis, indent=2)}"

    metadata_text = ""
    if patient_metadata:
        metadata_text = f"\nPATIENT METADATA:\n{json.dumps(patient_metadata, indent=2)}"

    return (
        f"STRUCTURED FINDINGS:\n{json.dumps(structured, indent=2)}\n"
        f"{prognosis_text}\n"
        f"{metadata_text}\n\n"
        f"INSTRUCTIONS: Generate region-mapped recovery recommendations. "
        f"For each affected region, provide:\n"
        f"1. Region name and its function\n"
        f"2. SHORT-TERM recommendations (immediate care priorities, medications, monitoring)\n"
        f"3. LONG-TERM recommendations (rehabilitation pathways, cognitive therapy, lifestyle factors)\n"
        f"4. Confidence level for each recommendation\n"
        f"Format as structured JSON with 'region', 'function', 'short_term', 'long_term', 'confidence' keys."
    )


def differential_diagnosis_prompt(structured: dict, etiology_hints: list[str] = None) -> str:
    """Generate differential diagnosis prompt from structured findings."""
    import json

    hints_text = ""
    if etiology_hints:
        hints_text = f"\nPOTENTIAL ETIOLOGIES TO CONSIDER: {', '.join(etiology_hints)}"

    return (
        f"STRUCTURED FINDINGS:\n{json.dumps(structured, indent=2)}\n"
        f"{hints_text}\n\n"
        f"INSTRUCTIONS: Generate a ranked differential diagnosis. "
        f"For each candidate etiology, provide:\n"
        f"1. Etiology name\n"
        f"2. Probability (0-1)\n"
        f"3. Evidence: which spatial features support this diagnosis\n"
        f"4. Which regions match the typical pattern for this etiology\n"
        f"5. Confidence level\n"
        f"Rank by probability. Never assign 100% probability to any single diagnosis."
    )


def connectivity_prompt(damage_summary: list[dict], tract_results: list[dict] = None,
                        network_results: list[dict] = None) -> str:
    """Generate connectivity disruption prompt."""
    import json

    context = f"DAMAGE SUMMARY:\n{json.dumps(damage_summary, indent=2)}"

    if tract_results:
        context += f"\n\nSTRUCTURAL CONNECTIVITY:\n{json.dumps(tract_results, indent=2)}"

    if network_results:
        context += f"\n\nFUNCTIONAL CONNECTIVITY:\n{json.dumps(network_results, indent=2)}"

    return (
        f"{context}\n\n"
        f"INSTRUCTIONS: Based on the damage and connectivity data, explain:\n"
        f"1. Which white matter tracts are disrupted and the functional impact\n"
        f"2. Which functional networks are affected and the clinical significance\n"
        f"3. How tract disruption relates to expected symptoms\n"
        f"4. Recovery potential for each disrupted pathway\n"
        f"Cite clinical literature where available."
    )


class PromptTemplates:
    """Backward-compatible class wrapper around module-level templates."""

    QA_SYSTEM_PROMPT = QA_SYSTEM_PROMPT
    REPORT_SYSTEM_PROMPT_CLINICIAN = REPORT_SYSTEM_PROMPT_CLINICIAN
    REPORT_SYSTEM_PROMPT_PATIENT = REPORT_SYSTEM_PROMPT_PATIENT
    PROGNOSIS_SYSTEM_PROMPT = PROGNOSIS_SYSTEM_PROMPT
    RECOVERY_SYSTEM_PROMPT = RECOVERY_SYSTEM_PROMPT

    qa_prompt = staticmethod(qa_prompt)
    clinician_report_prompt = staticmethod(clinician_report_prompt)
    patient_report_prompt = staticmethod(patient_report_prompt)
    prognosis_prompt = staticmethod(prognosis_prompt)
    rag_retrieval_prompt = staticmethod(rag_retrieval_prompt)
    voice_query_prompt = staticmethod(voice_query_prompt)
    recovery_prompt = staticmethod(recovery_prompt)
    differential_diagnosis_prompt = staticmethod(differential_diagnosis_prompt)
    connectivity_prompt = staticmethod(connectivity_prompt)
    get_template = staticmethod(lambda name: get_template(name))


# ── Template Registry ──

TEMPLATES = {
    "qa": qa_prompt,
    "clinician_report": clinician_report_prompt,
    "patient_report": patient_report_prompt,
    "prognosis": prognosis_prompt,
    "rag_retrieval": rag_retrieval_prompt,
    "voice_query": voice_query_prompt,
    "recovery": recovery_prompt,
    "differential_diagnosis": differential_diagnosis_prompt,
    "connectivity": connectivity_prompt,
}


def get_template(name: str):
    """Get a prompt template by name."""
    if name not in TEMPLATES:
        raise ValueError(f"Unknown template: {name}. Available: {list(TEMPLATES.keys())}")
    return TEMPLATES[name]