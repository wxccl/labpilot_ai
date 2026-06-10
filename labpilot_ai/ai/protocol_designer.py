def draft_protocol_suggestion(prompt: str, known_globals: dict | None = None, project_context: str | None = None) -> str:
    known_globals = known_globals or {}
    names = ", ".join(list(known_globals)[:12]) or "no registered globals yet"
    text = (prompt or "").strip()
    context = (project_context or "").strip()
    parts = [
        "# Protocol suggestion",
        "This page generates an experimental design suggestion only; it does not execute hardware actions.",
        f"Input summary: {text[:1200]}",
    ]
    if context:
        parts.append(f"Relevant project context:\n{context[:1800]}")
    parts.extend(
        [
            f"Available controllable globals include: {names}.",
            "Recommended workflow:\n"
            "1. Convert the scientific goal into a measurable lyse result.\n"
            "2. Register every adjustable runmanager variable with conservative ranges.\n"
            "3. Run a small grid scan in Dry run and then on hardware.\n"
            "4. Promote the best region to Bayesian optimization only after the lyse result is stable.\n",
        ]
    )
    return "\n\n".join(parts)
