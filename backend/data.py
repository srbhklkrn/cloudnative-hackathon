"""Fictional, deterministic data. No actual venue or speaker claims."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .models import Session

TALKS = [
    ("Inside Cilium's Datapath", "Follow a packet from a workload through kernel hooks and identity-aware routing. Learn how the extended Berkeley Packet Filter makes container traffic visible.", ["kubernetes", "networking", "ebpf"], "advanced"),
    ("A Safer Cluster, One Policy at a Time", "Start with workload identities, network policies and least privilege. A practical introduction to protecting containers.", ["kubernetes", "security"], "beginner"),
    ("The Golden Signals", "Understand latency, traffic, errors and saturation with a small instrumented application and distributed traces.", ["observability"], "beginner"),
    ("Serving Models Without Surprises", "Deploy inference workloads with sensible resource requests, batch sizes and capacity planning.", ["ai", "kubernetes"], "intermediate"),
    ("Git Is Your Control Plane", "Build a reproducible application delivery workflow with declarative state and reconciliation.", ["gitops", "platform"], "intermediate"),
    ("Packets, Policies and Pod Identity", "Investigate dropped traffic in a container cluster with kernel probes, flow records and Cilium tooling.", ["networking", "ebpf", "security"], "advanced"),
    ("Admission Control for Humans", "Write understandable admission policies and build a safe rollout process for a first cluster.", ["kubernetes", "security"], "beginner"),
    ("Tracing the Invisible", "Connect logs and request traces across service boundaries with OpenTelemetry and useful context propagation.", ["observability", "networking"], "intermediate"),
    ("GPU Scheduling Under Pressure", "Explore accelerator allocation, workload queues and practical inference serving tradeoffs.", ["ai", "platform"], "advanced"),
    ("Paved Roads That Teams Actually Use", "Design a developer platform around user research, feedback and a small set of self-service capabilities.", ["platform"], "beginner"),
    ("Kernel Superpowers for Cluster Traffic", "Use extended Berkeley Packet Filter programs to reveal service-to-service flows, investigate packet loss and enforce network identity.", ["ebpf", "networking", "kubernetes"], "advanced"),
    ("Workload Identity from Zero", "Replace long-lived credentials with short-lived identities. Learn the basics of service account security.", ["security", "kubernetes"], "beginner"),
    ("Why Was That Request Slow?", "Read a distributed trace, identify the slow dependency and measure whether a change helped.", ["observability"], "intermediate"),
    ("Vector Search for Platform Engineers", "Understand retrieval, embeddings and evaluating relevance for infrastructure documentation.", ["ai", "platform"], "beginner"),
    ("Safe Releases with Argo CD", "Use health checks, progressive delivery and rollback evidence to ship changes safely.", ["gitops", "kubernetes"], "intermediate"),
    ("Seeing Traffic Without Sidecars", "Observe container connections directly from the Linux kernel. Explore network flow visibility and the tradeoffs of probe-based telemetry.", ["ebpf", "networking", "observability"], "advanced"),
    ("Container Security: Your First Hour", "Learn image hygiene, pod permissions and network isolation with approachable hands-on examples.", ["security", "kubernetes"], "beginner"),
    ("An SLO Is a Conversation", "Turn user expectations into service-level objectives, error budgets and useful alerts.", ["observability", "platform"], "beginner"),
    ("The Cost of an AI Request", "Measure model-serving latency, token usage and infrastructure cost with end-to-end instrumentation.", ["ai", "observability"], "intermediate"),
    ("Platform APIs That Age Well", "Choose stable platform interfaces and avoid building a portal for every infrastructure operation.", ["platform", "gitops"], "advanced"),
    ("Following a Packet Across the Cluster", "Inspect service routing, address translation and dropped connections using Cilium's flow visibility and kernel instrumentation.", ["networking", "ebpf", "kubernetes"], "advanced"),
    ("Secrets Are a Lifecycle", "Rotate credentials safely, limit application access and build understandable recovery procedures.", ["security", "platform"], "intermediate"),
    ("Profiles Complete the Picture", "Use continuous profiling alongside logs, metrics and traces to find CPU and memory bottlenecks.", ["observability"], "advanced"),
    ("Small Models, Useful Agents", "Design bounded agent workflows and evaluate whether smaller models meet your task requirements.", ["ai"], "beginner"),
    ("GitOps Beyond the Happy Path", "Understand drift, failed reconciliation, dependency ordering and recovery during a broken release.", ["gitops", "kubernetes"], "advanced"),
    ("Network Policy: From Intent to Packets", "Translate a security boundary into network policies and verify actual enforcement with kernel flow evidence.", ["networking", "security", "ebpf"], "intermediate"),
    ("Threat Modeling a Cluster", "Map trust boundaries, identify likely attack paths and prioritize a small set of practical defenses.", ["kubernetes", "security"], "beginner"),
    ("Telemetry You Can Afford", "Keep useful signals with intentional sampling, cardinality budgets and predictable retention.", ["observability", "platform"], "intermediate"),
    ("Reliable Retrieval in Production", "Evaluate hybrid retrieval, handle indexing failures and monitor a search-backed assistant.", ["ai", "observability"], "advanced"),
    ("A Platform Is a Product", "Build a feedback loop from developer needs to measurable improvements in delivery and reliability.", ["platform", "gitops"], "beginner"),
]


def seed_sessions() -> list[Session]:
    sessions = []
    for i, (title, abstract, topics, level) in enumerate(TALKS):
        slot, room = divmod(i, 5)
        hour = [9, 10, 11, 13, 14, 15][slot]
        start = datetime(2026, 11, 9, hour, tzinfo=ZoneInfo("America/Denver"))
        sessions.append(Session(
            id=f"session-{i + 1:02d}", title=title, abstract=abstract,
            speaker=f"Demo Speaker {i + 1:02d}", topics=topics, level=level,
            start=start, end=start + timedelta(minutes=45),
            room=["Aspen", "Juniper", "Cedar", "Willow", "Pine"][room],
            building="Summit" if room < 3 else "Canyon",
            accessibility={"step_free": room != 4, "captions": room in [0, 1, 2],
                           "hearing_loop": room in [0, 2], "quiet_space": room in [1, 3]},
        ))
    return sessions
