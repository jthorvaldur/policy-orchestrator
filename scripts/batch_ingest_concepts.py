#!/usr/bin/env python3
"""Batch generate stub .md files for newly-mined concepts and run them through
the unified update pipeline (ingest → catalog → regen pages).

The 34 concepts below were produced by three parallel mining agents on
2026-06-03. Each entry has the abstract pattern only — no personal data,
no author attribution. The stub format gives each concept enough body to be
semantically searchable in legal_concepts while keeping it concise (~300 words
per file). Full algo treatments can be expanded later.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

OUT_DIR = Path.home() / "GitHub" / "caseledger" / "docs" / "concept_stubs"
INGEST_SCRIPT = Path(__file__).parent / "update_concept.py"

CONCEPTS: list[dict] = [
    # ──────────────────── BEHAVIORAL / INFLUENCE ────────────────────
    {
        "concept_id": "authority_monopoly_prevention",
        "title": "Authority Monopoly Prevention",
        "layer": "vocab",
        "target": ["opposing_counsel", "judge", "witness", "self"],
        "venue": ["settlement", "hearing", "deposition"],
        "leverage": 3,
        "tempo": "preemptive",
        "brief": "Detect and disrupt attempts to create one-way access to information or decision-making power through gatekeeper narratives.",
        "precondition": "Counterparty claims exclusive knowledge or sole-translator access to a domain.",
        "anti_pattern": "Accepting framing that opponent is sole translator of facts.",
        "body": "When any actor in a case (opposing counsel, opposing party, advisor, intermediary) positions themselves as the exclusive interpreter of a domain — finances, the children's needs, what the judge wants — the framing itself is the trap. The move is to verify independently and refuse the gatekeeper role. State explicitly: I will map the coordinate myself. Independence is restored by action (own bank pulls, own ledger, own statutory research), not by assertion. The vocabulary that signals deployment: 'verify independently', 'map your own coordinate', 'self-sufficiency not dependence'.",
    },
    {
        "concept_id": "coherence_consistency_test",
        "title": "Coherence Consistency Test",
        "layer": "L1_demand",
        "target": ["opposing_counsel", "judge", "advisor_subprocess"],
        "venue": ["interpersonal", "deposition", "settlement"],
        "leverage": 4,
        "tempo": "parallel",
        "brief": "Assess whether counterparty's stated values match observed actions across multiple behavioral domains; mask slips reveal in delta.",
        "precondition": "Extended behavioral observation is possible (multiple interactions, multiple domains).",
        "anti_pattern": "Taking verbal commitments at face value without action verification.",
        "body": "Stated values and observed actions diverge under stress. The diagnostic is to score each across at least three independent domains (treatment of subordinates / treatment of people who can do nothing for them / behavior under criticism / consistency over weeks not minutes) and measure the delta. Large delta = coherence break = credibility discount. The value of this is not in catching anyone in a single instance; it is in producing a coherence index that can be tracked over time, where the trend itself is the signal.",
    },
    {
        "concept_id": "micropattern_extraction_early_detection",
        "title": "Micropattern Extraction — Early Detection",
        "layer": "L1_demand",
        "target": ["opposing_counsel", "witness", "judge"],
        "venue": ["deposition", "interpersonal", "hearing"],
        "leverage": 4,
        "tempo": "reactive",
        "brief": "Identify linguistic tells and body-signal precursors of deceptive intent before mask failure via high-resolution behavioral sampling.",
        "precondition": "Real-time behavioral access (in person, on video, in transcribed deposition).",
        "anti_pattern": "Relying on stated intent or self-reported emotion; trusting words over micro-signals.",
        "body": "Deception precedes itself with measurable micropatterns: gaze re-anchoring before a known-false statement, lateral hand movement during disclaimer, gratuitous adjective insertion, reflexive smile after a fact assertion. The deposition application is to seed early questions where ground-truth is known to you and observe baseline. Then ask the question that matters. The micropatterns that appeared in the baseline-known segment recur or change at the contested segment; the delta is signal. None of this is courtroom evidence. It is internal-strategy signal that guides which threads to pull further.",
    },
    {
        "concept_id": "emotional_dysregulation_leverage",
        "title": "Emotional Dysregulation Window",
        "layer": "L2_refuse",
        "target": ["opposing_counsel", "counterparty"],
        "venue": ["settlement", "interpersonal", "hearing"],
        "leverage": 4,
        "tempo": "reactive",
        "brief": "Detect precision windows of emotional volatility that degrade opponent decision-making and exploit them for forced suboptimal choices.",
        "precondition": "Access to behavioral or physiological indicators (response latency, communication tone, prior pattern).",
        "anti_pattern": "Expecting consistent rational response from a dysregulated counterparty.",
        "body": "Stress narrows cognition. Sleep loss, prior emotional escalation, public criticism, and ego threat all create predictable windows in which the counterparty's decision quality drops. The use is not to trigger dysregulation — that creates reactance and damages the long game. The use is to recognize when a window is open (escalating email cadence, unforced procedural errors, repeated demands) and time consequential offers for that window so they are evaluated under degraded judgment. Track dysregulation onset and recovery half-life as case-state variables.",
    },
    {
        "concept_id": "momentum_cascade_filing",
        "title": "Momentum Cascade Filing",
        "layer": "L3_expose",
        "target": ["opposing_counsel", "judge", "counterparty"],
        "venue": ["filing", "hearing"],
        "leverage": 4,
        "tempo": "parallel",
        "brief": "Coordinated multi-front motion waves that exceed opponent's cognitive load and counsel's cost-tolerance.",
        "precondition": "Genuine claim multiplicity and procedural grounds across distinct domains.",
        "anti_pattern": "Single-motion approach allows focused response; barrage without merit triggers bad-faith findings.",
        "body": "Filings in isolation are answerable. Coordinated filings across multiple domains within a narrow window exceed the counter-side's ability to respond on any one with adequate preparation. The composition is critical: each filing must be substantively meritorious; the cascade is the strategic frame. The judge reads the volume as productive; counsel reads it as billable-time crisis; counterparty reads it as inability to keep up. None of these readings are wrong. Only deploy with prepared filings already drafted before the trigger event.",
    },
    {
        "concept_id": "negative_sum_frame_shift",
        "title": "Negative-Sum Reframing",
        "layer": "vocab",
        "target": ["opposing_counsel", "judge", "counterparty", "advisor_subprocess"],
        "venue": ["settlement", "interpersonal"],
        "leverage": 4,
        "tempo": "preemptive",
        "brief": "Convert zero-sum framing (your gain = my loss) into negative-sum (both sides erode shared pool through extended conflict).",
        "precondition": "Verifiable cost structure and finite asset pool.",
        "anti_pattern": "Framing as winner-take-all encourages prolonged litigation; framing as threat collapses the move.",
        "body": "Adversarial litigation defaults to zero-sum framing: every dollar to the other side is a dollar lost. Reality is negative-sum: lawyer fees, court costs, time, opportunity cost, and stress depletion all leave less for both sides than existed at the start. The reframing makes settlement rational without making it a concession. Vocabulary: 'the marital estate is a finite pool / the longer this runs the less divides / this is a negative-sum game disguised as zero-sum.' Most effective with sophisticated counsel and judges; weakest with personality-driven counterparties for whom the dispute itself is the payoff.",
    },
    {
        "concept_id": "leverage_choice_framing",
        "title": "Leverage as Choice, Not Threat",
        "layer": "vocab",
        "target": ["opposing_counsel"],
        "venue": ["settlement", "interpersonal"],
        "leverage": 4,
        "tempo": "reactive",
        "brief": "Present settlement as a choice between two distinct paths (negotiated exit or filed motions), forcing counsel to advise rather than bill.",
        "precondition": "Genuine documented leverage + clear deadline + attorney as recipient.",
        "anti_pattern": "Phrasing as threat activates defensive/escalation reflex; weak leverage exposes the framing.",
        "body": "A threat puts opposing counsel in a defensive posture and gives them no reason to advise their client to accept. A choice — laid out in a memo, with documents attached, with a deadline — gives counsel an artifact to take to their client. The two paths must both be real (we settle on these terms OR we file these motions on this date with these documents); the recipient is opposing counsel, not the counterparty. The aim is to convert the lawyer from billing agent into advising agent for one critical conversation with their client.",
    },
    {
        "concept_id": "credential_collapse_documentary",
        "title": "Credential Collapse via Documentary Contradiction",
        "layer": "L3_expose",
        "target": ["judge", "opposing_counsel", "counterparty"],
        "venue": ["filing", "hearing"],
        "leverage": 5,
        "tempo": "reactive",
        "brief": "Demolish credibility through exhaustive cross-referencing of contradictions in opponent's own documents, exhibits, and sworn statements.",
        "precondition": "Comprehensive documentary record across multiple filings of opposing party.",
        "anti_pattern": "Single contradiction allows selective response; airing contradictions before they are stacked dilutes impact.",
        "body": "One contradiction is a mistake. Ten is a pattern. Thirty is fraud. The mechanics: catalog every numeric claim, every date, every account reference, every party identifier across the opposing party's filings. Index by claim and by filing date. Highlight the contradictions in a single annotated table. The collapse is not about the individual contradictions; it is about the table itself. Once the judge sees the table, individual rebuttal is futile.",
    },
    {
        "concept_id": "trigger_point_mapping",
        "title": "Trigger Point Mapping",
        "layer": "L2_refuse",
        "target": ["counterparty", "opposing_counsel"],
        "venue": ["settlement", "interpersonal", "deposition"],
        "leverage": 3,
        "tempo": "reactive",
        "brief": "Identify and document the specific persons, phrases, or situations that reliably trigger counterparty emotional dysregulation.",
        "precondition": "Sufficient historical interaction data to identify reliable triggers.",
        "anti_pattern": "Overuse desensitizes the trigger; deliberate deployment burns trust and invites ethical scrutiny.",
        "body": "Some specific subjects reliably destabilize the counterparty's decision-making: family member mentions, prior-relationship references, financial-control challenges, status threats. Map the triggers internally as case-state knowledge. Use is mostly defensive: in deposition, expect that the counterparty will introduce these subjects as misdirection. Recognize the trigger pattern as it appears in real-time and refuse to follow into the emotional content. Deliberate offensive deployment carries cost: it works briefly and damages the long-game record.",
    },
    {
        "concept_id": "settlement_rejection_narrative",
        "title": "Settlement Rejection as Control Signal",
        "layer": "vocab",
        "target": ["judge", "advisor_subprocess", "counterparty_counsel"],
        "venue": ["hearing", "filing"],
        "leverage": 3,
        "tempo": "reactive",
        "brief": "Frame counterparty's rejection of an objectively favorable settlement as control-seeking rather than money-seeking.",
        "precondition": "Settlement offer is objectively favorable on standard family-court math.",
        "anti_pattern": "Characterizing rejection as irrational without framework; reads as sour grapes.",
        "body": "When the counterparty rejects an offer that exceeds what a court would order, the rejection itself is evidence about motivation. The narrative move is to note (in pretrial memorandum, in hearing argument) that the offer exceeded standard maintenance and child-support norms; the rejection therefore reveals goal-misalignment between stated and actual objectives. The judge reads this as the counterparty fighting for control rather than fighting for resources, which shifts judicial weighting.",
    },
    {
        "concept_id": "procedure_compliance_signal",
        "title": "Procedural Compliance as Credibility Signal",
        "layer": "L1_demand",
        "target": ["judge"],
        "venue": ["filing", "hearing"],
        "leverage": 3,
        "tempo": "parallel",
        "brief": "Meticulous procedural compliance signals credibility to judge while forcing opponent into procedural error.",
        "precondition": "Capacity to maintain clean procedural record across every filing and deadline.",
        "anti_pattern": "Procedural sloppiness on your side undermines the substantive case; a single missed deadline collapses the signal.",
        "body": "The judge watches procedural hygiene as a proxy for credibility on substance. Every filing properly captioned, every deadline met, every certificate of service complete, every exhibit numbered: each is a low-cost credibility deposit. Over the case lifecycle, deposits accumulate. The corollary is that opposing-side sloppiness is read as substantive weakness too. Use this asymmetry by noting (in motions, with restraint) specific procedural defects in opposing filings.",
    },
    {
        "concept_id": "behavioral_coordinate_mapping",
        "title": "Three-Axis Behavioral Coordinate",
        "layer": "meta",
        "target": ["opposing_counsel", "counterparty", "judge"],
        "venue": ["interpersonal"],
        "leverage": 4,
        "tempo": "parallel",
        "brief": "Map any actor on three independent axes (autonomy↔control, coherence↔fragmentation, other-focus↔self-focus) for response prediction.",
        "precondition": "Sufficient observational data across multiple contexts.",
        "anti_pattern": "Assuming monolithic personality across contexts; freezing the coordinate as static.",
        "body": "Single-axis personality models miss interaction effects. The three-axis coordinate: f1 measures whether the actor responds to autonomy or to control; f2 measures whether the actor's behavior is coherent across contexts or fragmented; f3 measures whether attentional gravity is other-focused or self-focused. Each axis scored 1-5. The triple coordinate predicts response patterns across novel situations. Update as new data arrives. The most useful application is internal: who in this case operates at (4,4,3) vs (2,1,5) and how do their decision functions differ?",
    },
    {
        "concept_id": "extractive_mask_vulnerability",
        "title": "Extractive Mask — Pre-Slip Detection",
        "layer": "L1_demand",
        "target": ["opposing_counsel", "witness", "advisor_subprocess"],
        "venue": ["interpersonal", "deposition"],
        "leverage": 3,
        "tempo": "preemptive",
        "brief": "Identify persons deploying covert extraction tactics through their specific pre-slip linguistic patterns.",
        "precondition": "Early access to communication patterns over multiple interactions.",
        "anti_pattern": "Waiting for obvious extraction evidence allows the mask to fully embed.",
        "body": "Covertly extractive actors leak the pattern through micro-linguistic tells before the extraction occurs: rapid rapport escalation, inappropriate intimacy timing, unilateral credibility claims, future-promise density per minute of conversation. Early recognition allows pre-emptive distance without confrontation. The risk profile: false positives are recoverable; false negatives are not. Bias toward early-stage distance, with the option to re-engage if observation contradicts the pattern.",
    },
    {
        "concept_id": "mutual_destruction_parity",
        "title": "Mutual-Exposure Parity",
        "layer": "L3_expose",
        "target": ["opposing_counsel", "counterparty"],
        "venue": ["filing"],
        "leverage": 4,
        "tempo": "reactive",
        "brief": "Establish symmetric cost structure where both sides have equal exposure, removing asymmetric leverage.",
        "precondition": "The counterparty has material exposure (financial, reputational, regulatory) you can document.",
        "anti_pattern": "Asymmetric exposure allows the counterparty to pursue indefinitely.",
        "body": "Asymmetric exposure is the engine that drives extended litigation. When one side has nothing material to lose, every motion is free for them. The countermove is to construct symmetric exposure: mutual disclosure demands, mutual release structures, parallel ARDC tracks against both counsels if conduct supports it, reciprocal sanctions exposure. Once the math is symmetric, the rational move for both sides is settlement.",
    },

    # ──────────────────── GAME THEORY / NEGOTIATION ────────────────────
    {
        "concept_id": "finite_pool_negative_sum_reframing",
        "title": "Finite-Pool Negative-Sum Reframing",
        "layer": "phil",
        "target": ["counterparty", "judge"],
        "venue": ["settlement", "mediation"],
        "leverage": 3,
        "tempo": "preemptive",
        "brief": "Convert zero-sum framing into negative-sum to create mutual incentive for exit over prolonged conflict.",
        "precondition": "Opposing party remains engaged in extended litigation; estate value is finite.",
        "anti_pattern": "Framing as threat collapses the cooperative read.",
        "body": "Closely related to negative_sum_frame_shift but specifically targeted at mediated-settlement framing. Highlight the calendar math: monthly burn rate × months remaining = pool depletion. Make the depletion visible in a single chart shared with mediator. The chart converts conflict from outcome contest to time contest. The party with less appetite for time loss tends to move first.",
    },
    {
        "concept_id": "information_leverage_settlement_forcing",
        "title": "Information Leverage → Forced Settlement",
        "layer": "L2_refuse",
        "target": ["opposing_counsel", "counterparty"],
        "venue": ["settlement"],
        "leverage": 4,
        "tempo": "preemptive",
        "brief": "Deploy disclosed asymmetric information to force mediated settlement; create binary choice (settle vs. public exposure).",
        "precondition": "Asymmetric information exists (undisclosed accounts, false affidavits, regulatory exposure).",
        "anti_pattern": "Using information as threat triggers escalation; deploy as settlement catalyst, not weapon.",
        "body": "Information that has not yet been entered in the record retains optionality. Once filed, it is consumed. The leverage is in the choice. Present the information to opposing counsel in a settlement memo with two paths: settle on these terms by date X, or the information becomes part of the public record on date X+1. The framing is neutral; the math does the work.",
    },
    {
        "concept_id": "documented_defection_pattern_recognition",
        "title": "Documented Defection Pattern",
        "layer": "L1_demand",
        "target": ["judge", "opposing_counsel"],
        "venue": ["filing", "hearing"],
        "leverage": 4,
        "tempo": "parallel",
        "brief": "Build a visible record of opposing-side defection to signal that escalation is justified.",
        "precondition": "Multiple documented violations; pattern is evident across filings.",
        "anti_pattern": "Presenting isolated incidents; loses effect unless pattern is clearly indexed.",
        "body": "Defection in repeated games shifts cooperative equilibria. The court's perception of which side is defecting controls who carries the discretionary downside. Build an indexed record of defections: deadline missed, disclosure withheld, communication ignored. Each is small. The index is the move.",
    },
    {
        "concept_id": "cooperative_signal_through_procedural_restraint",
        "title": "Cooperative Signal via Restraint",
        "layer": "L1_demand",
        "target": ["judge"],
        "venue": ["filing", "hearing"],
        "leverage": 2,
        "tempo": "preemptive",
        "brief": "Demonstrate willingness to settle via measured motion language and explicit cooperation statements.",
        "precondition": "The judge is in active decision role; opposing party reads as escalatory in the record.",
        "anti_pattern": "Mixed signals (restrained language + aggressive filings) collapse credibility.",
        "body": "The judge watches tone. Restraint in language signals you are not the escalation source even when the substantive content is aggressive. The language frame: 'Petitioner respectfully requests', 'in the interest of resolution', 'absent voluntary compliance' — all of these read as cooperative while making firm demands. The asymmetry is the point: substance is firm, tone is restrained, opposing-side tone is hostile.",
    },
    {
        "concept_id": "motion_sequencing_ambush",
        "title": "Motion Sequencing Ambush",
        "layer": "L2_refuse",
        "target": ["counterparty", "opposing_counsel", "judge"],
        "venue": ["filing"],
        "leverage": 3,
        "tempo": "reactive",
        "brief": "File fewer, heavier, fully-documented motions in strategic sequence to minimize response time.",
        "precondition": "Documentary evidence already assembled; procedural rules allow staggered filing.",
        "anti_pattern": "Blizzard of weak motions triggers bad-faith findings.",
        "body": "Strong motions in sequence beat weak motions in volume. Each filing carries its own documentary record and answers itself. Sequence the filings so the second arrives before the first is answered. The compounding effect: opposing counsel cannot respond to motion 2 until they have answered motion 1, but motion 1's answer creates new exposure that motion 3 will exploit.",
    },
    {
        "concept_id": "financial_affidavit_as_leverage_weapon",
        "title": "Financial Affidavit as Primary Weapon",
        "layer": "L1_demand",
        "target": ["counterparty", "judge"],
        "venue": ["filing", "hearing"],
        "leverage": 5,
        "tempo": "preemptive",
        "brief": "Target false or incomplete financial affidavits as primary weapon — credibility plus order-foundation in one strike.",
        "precondition": "Affidavit contains material false statements or omissions; supporting documentation exists.",
        "anti_pattern": "Diluting focus by attacking tangential issues; the FDA is the strike zone.",
        "body": "In family law, the FDA is the foundation of every downstream order. If the FDA is materially false, every order built on it is on weak ground. Attack the FDA directly with documentary evidence (bank records, tax returns, third-party documents). Do not attack tangential issues until the FDA is collapsed; tangential attacks dilute the primary lever.",
    },
    {
        "concept_id": "threshold_triggered_disclosure_sequencing",
        "title": "Threshold-Triggered Motion Cascade",
        "layer": "L2_refuse",
        "target": ["counterparty", "judge"],
        "venue": ["filing"],
        "leverage": 3,
        "tempo": "reactive",
        "brief": "Hold pre-drafted motion cascade until a documentary trigger event (opposing-side filing), then release as 'response'.",
        "precondition": "Pre-drafted motion cascade ready; clear threshold trigger identifiable.",
        "anti_pattern": "Premature release reads as premeditation rather than response.",
        "body": "Motions that look responsive read as more legitimate than motions that look strategic. Pre-draft the cascade. Identify the trigger event in opposing-side filings (false affidavit, contempt petition, discovery default). When the trigger fires, release the cascade as 'response to'. The substance is the same; the framing is different; the judge reads them as reactive rather than aggressive.",
    },
    {
        "concept_id": "sworn_statement_burden_shift",
        "title": "Sworn Statement Burden Shift",
        "layer": "L1_demand",
        "target": ["counterparty", "judge"],
        "venue": ["filing", "hearing"],
        "leverage": 2,
        "tempo": "preemptive",
        "brief": "Convert arguments into sworn affidavits to shift evidentiary burden onto opposing party.",
        "precondition": "Facts are documented and sworn; opposing party has motive to rebut.",
        "anti_pattern": "Affidavits without supporting documentation lose evidentiary weight.",
        "body": "Argumentative briefs invite counter-argument. Sworn statements require counter-affidavits or counterparty admission by silence. The conversion is mechanical: take the strongest argumentative points, restate as numbered factual assertions under oath, attach supporting documents. Now opposing party must file counter-affidavits with their own documents — or concede.",
    },
    {
        "concept_id": "procedural_exhaustion_attrition",
        "title": "Procedural Exhaustion as Attrition",
        "layer": "L3_expose",
        "target": ["counterparty", "opposing_counsel"],
        "venue": ["filing"],
        "leverage": 3,
        "tempo": "parallel",
        "brief": "Use procedural rules (continuances, discovery disputes) as natural attrition without appearing to cause delay.",
        "precondition": "Court is backlogged; counterparty is resource-constrained.",
        "anti_pattern": "Appearing to deliberately delay triggers sanctions or fee-shifting.",
        "body": "Time favors the party with longer runway. Procedural rules supply legitimate friction (continuances on health/scheduling grounds, discovery disputes that cannot be resolved without hearing, requests for clarification). Each use is small; the cumulative effect across months is substantial. The frame is always procedural-good-faith. Deliberate-delay framing collapses the entire approach into sanctions exposure.",
    },
    {
        "concept_id": "system_extraction_loop_exit",
        "title": "System Extraction Loop — Exit Path",
        "layer": "phil",
        "target": ["counterparty", "mediator"],
        "venue": ["settlement", "mediation"],
        "leverage": 2,
        "tempo": "preemptive",
        "brief": "Identify the system's structural incentive to maximize extraction; settlement is the only exit.",
        "precondition": "Both parties recognize escalating litigation costs; system incentives are transparent.",
        "anti_pattern": "Presenting as ultimatum loses legitimacy.",
        "body": "The litigation system has structural incentives to prolong: judges optimize for docket clearance which favors settlement only when both sides agree; counsel optimize for fees which favor extension; experts optimize for engagements which favor complexity. The exit is a negotiated settlement; everything else is variation on the extraction. Make this visible to all parties as shared problem rather than adversarial frame.",
    },
    {
        "concept_id": "discovery_gap_foundational_challenge",
        "title": "Discovery Gap as Foundational Challenge",
        "layer": "L1_demand",
        "target": ["judge"],
        "venue": ["filing", "hearing"],
        "leverage": 4,
        "tempo": "preemptive",
        "brief": "Frame incomplete financial disclosure as foundational defect that taints all downstream orders.",
        "precondition": "Disclosure is provably incomplete; prior orders were entered relying on it.",
        "anti_pattern": "Attacking orders directly is less effective than attacking the foundational disclosure.",
        "body": "Downstream orders that depend on incomplete disclosure are vulnerable to vacation on the disclosure ground alone. The attack: motion to compel complete disclosure; on grant, motion to reconsider prior orders entered without the now-required information. The two motions in sequence force the court to either grant both or be inconsistent.",
    },

    # ──────────────────── SYSTEMS / META ────────────────────
    {
        "concept_id": "forcing_function_procedural",
        "title": "Forcing Function — Procedural",
        "layer": "L2_refuse",
        "target": ["opposing_counsel", "judge"],
        "venue": ["filing"],
        "leverage": 4,
        "tempo": "reactive",
        "brief": "Procedural mechanism requiring opponent to produce auditable response; engagement validates, non-engagement creates record gap.",
        "precondition": "Well-pleaded factual assertions with documentary support and timely service.",
        "anti_pattern": "Rhetorical questions; unsupported assertions; vague demands.",
        "body": "Every assertion in a filing is either engaged-with or ignored. Number each assertion; tag each with status ('UNDISPUTED unless denied within X days'). The structure forces a binary: counsel must engage or face deemed-admission. Engagement validates your framework; non-engagement builds the record gap. Either path is your win.",
    },
    {
        "concept_id": "record_checkpoint_saturation",
        "title": "Record Checkpoint Saturation",
        "layer": "L2_refuse",
        "target": ["judge"],
        "venue": ["filing"],
        "leverage": 3,
        "tempo": "parallel",
        "brief": "Periodic status table documenting which assertions have been undisputed; temporal non-denial hardens the record.",
        "precondition": "Sustained filing cycle with numbered assertions in prior filings.",
        "anti_pattern": "Sporadic filings; unnumbered assertions; failure to track opponent denials.",
        "body": "Every 60-90 days, file a status table: every numbered assertion from prior filings, its date, opposing-side response (or absence), current status (UNDISPUTED / DENIED / CONTESTED). The judge sees a running scoreboard. At ~90 days of non-denial, the assertion hardens into the record. The scoreboard itself shifts the burden of going forward.",
    },
    {
        "concept_id": "escalation_ladder_saturation",
        "title": "Escalation Ladder — Saturation Discipline",
        "layer": "L1_demand",
        "target": ["judge"],
        "venue": ["filing"],
        "leverage": 3,
        "tempo": "preemptive",
        "brief": "Five-rung progression (establish facts → patterns → structure → quantify → close record) matching filing intensity to case maturity.",
        "precondition": "Mathematical/structural backing available; disciplined filing rate.",
        "anti_pattern": "Leading with exotic content; under-saturation leaving structure invisible.",
        "body": "Saturation is a resource. Deploy it with discipline: months 1-3 establish basic facts; months 3-6 establish patterns across facts; months 6-12 introduce structure (rules, framework); months 12-18 quantify damages; months 18+ close the record. Skipping rungs reads as premature. Repeating rungs reads as confused. The judge's clerk begins to notice the structure and treats your filings with more weight.",
    },
    {
        "concept_id": "appellate_leverage_record_auditability",
        "title": "Appellate Leverage via Auditable Record",
        "layer": "L3_expose",
        "target": ["judge"],
        "venue": ["appeal", "filing"],
        "leverage": 3,
        "tempo": "endgame",
        "brief": "Trial record that is formally auditable (numbered chains, citations) outweighs opposing narrative in appellate review.",
        "precondition": "Trial record sufficiently structured; documented opponent narrative gaps.",
        "anti_pattern": "Purely narrative record; opponent with mathematical sophistication; trial judge with explicit reasoning.",
        "body": "Appellate courts reconstruct cases from the trial record. A record where one side's filings are numbered, citation-anchored, and cross-referenced — and the other side's are narrative — reconstructs in the auditable side's favor. The leverage is structural: not the threat of appeal but the fact that any reviewing court will read your record as more reliable.",
    },
    {
        "concept_id": "burden_shift_prima_facie_collapse",
        "title": "Burden-Shift Prima Facie Collapse",
        "layer": "L2_refuse",
        "target": ["judge"],
        "venue": ["filing", "hearing"],
        "leverage": 4,
        "tempo": "reactive",
        "brief": "Opponent's prima facie case contradicts itself across filings; threshold failure prevents burden shift to defendant.",
        "precondition": "Opposing party has made multiple sworn quantifications with material variance.",
        "anti_pattern": "Single, consistent opposing claim; fact-intensive rather than legal threshold.",
        "body": "Burden-shifting doctrines require a specific prima facie showing. When the showing varies materially across opposing-side filings (different dollar amounts, different account identifiers, different time windows), the threshold is unmet and burden never shifts. The motion: point out the specific variance; cite the specificity doctrine; ask the court to find that no prima facie showing has been made. This is a clean legal-threshold attack rather than a fact contest.",
    },
    {
        "concept_id": "admission_netting_offset_defense",
        "title": "Admission Netting / Offset Defense",
        "layer": "L2_refuse",
        "target": ["judge"],
        "venue": ["filing", "hearing"],
        "leverage": 4,
        "tempo": "reactive",
        "brief": "Strategic recharacterization: opponent's admitted facts simultaneously establish both claimed damages and defensible offset.",
        "precondition": "Opponent's own verified admissions in filings; documentary chain.",
        "anti_pattern": "Purely inferential argument; opponent maintains consistency.",
        "body": "Opposing party's admissions can be re-characterized so they serve both their claim AND your offset. The trap: 'Either these funds were support owed to my client (in which case they offset the arrearage) or they were dissipation into your client's solely-owned entity (in which case they add to the estate against your client). You cannot have it both ways.' Forces a binary that damages opposing-side credibility on either branch.",
    },
    {
        "concept_id": "triple_axis_pressure_independence",
        "title": "Triple-Axis Independent Pressure",
        "layer": "L1_demand",
        "target": ["judge", "opposing_counsel", "regulator"],
        "venue": ["filing", "regulatory"],
        "leverage": 3,
        "tempo": "parallel",
        "brief": "Three independent procedural vectors (constitutional, statutory, ethical) on distinct targets; asymmetric escalation options.",
        "precondition": "Contempt liability + statutory claims + rule violations against same party/counsel.",
        "anti_pattern": "Single-axis argument; merits-only framing; failure to decompose pressure vectors.",
        "body": "Constitutional defense (Turner-style required findings) operates on judicial authority. Statutory claims operate on equitable distribution. Ethical violations (RPC) operate on counsel's professional duty. Each is independent; each creates pressure the others do not. Deploy in parallel so the opposing side cannot defend on a single front.",
    },
    {
        "concept_id": "documented_contradiction_impeachment",
        "title": "Documentary Self-Impeachment",
        "layer": "L2_refuse",
        "target": ["counterparty", "judge"],
        "venue": ["filing", "discovery"],
        "leverage": 4,
        "tempo": "reactive",
        "brief": "Self-impeachment via opponent's own documents: sworn affidavit omits an account that later filing admits.",
        "precondition": "Two opposing-side filings, same subject, material variance, both dated.",
        "anti_pattern": "Inference-based argument; single document; airing the contradiction before opponent has committed both sides.",
        "body": "Cleanest credibility attack: one filing pretends an account or fact does not exist; a later filing references it. Both are signed under oath. There is no inference required and no narrative argument needed; the contradiction is on the face of the documents. Cite both, side by side, in motion practice or in a deposition outline. The opposing side cannot reconcile without admitting one of the two filings was false.",
    },
]


def write_stub(c: dict) -> Path:
    cid = c["concept_id"]
    path = OUT_DIR / f"{cid}.md"

    target = c.get("target", [])
    venue = c.get("venue", [])

    frontmatter = f"""---
concept_id: {cid}
doc_type: algorithm
case_id: universal
applicable_cases: [universal]
factor_layer: {c.get('layer', '')}
factor_leverage: {c.get('leverage', 3)}
factor_target: {target}
factor_venue: {venue}
factor_tempo: {c.get('tempo', 'parallel')}
factor_jurisdiction: [universal]
abstraction_level: fully-abstract
---

# {c['title']}

## Brief

{c['brief']}

## Mechanics

{c['body']}

## Precondition

{c['precondition']}

## Anti-pattern

{c['anti_pattern']}
"""
    path.write_text(frontmatter, encoding="utf-8")
    return path


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Writing {len(CONCEPTS)} concept stubs to {OUT_DIR}")
    paths = [write_stub(c) for c in CONCEPTS]
    print(f"  wrote {len(paths)} files")

    print(f"\nRunning update_concept.py on all {len(paths)} stubs...")
    cmd = ["uv", "run", "python", str(INGEST_SCRIPT)] + [str(p) for p in paths]
    subprocess.run(cmd, check=True, cwd=Path(__file__).parent.parent)


if __name__ == "__main__":
    main()
