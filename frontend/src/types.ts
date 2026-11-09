export type Session = {
  id: string; title: string; abstract: string; speaker: string; topics: string[];
  level: string; start: string; end: string; room: string; building: string;
  status: 'scheduled' | 'canceled'; capacity_state: 'available' | 'full';
  accessibility: Record<string, boolean | null>; accessibility_verified_demo: boolean; revision: number;
};
export type Preferences = { topics: string[]; accessibility: string[] };
export type Agenda = { session_ids: string[]; preferences: Preferences; accepted_alternatives: {original_id: string; replacement_id: string}[] };
export type Affected = { session_id: string; session: Session | null; reason: string };
export type AgendaResponse = { agenda: Agenda; sessions: Session[]; affected: Affected[] };
export type Recommendation = { session: Session; explanation: string[]; relevance: number; accessibility: string };
export type Plan = { disruption: Affected | null; recommendations: Recommendation[]; remaining_disruptions: number; message: string | null; mode: string };
export type Meta = { store: string; ready: boolean; semantic_search: boolean; topics: string[]; version: string; inference_id: string | null; telemetry_configured: boolean };
export type Event = { id: string; session_id: string; event_type: string; timestamp: string };
